from __future__ import annotations

import signal
import time
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

from moontransfer.progress import (
    TransferProgressSample,
    format_duration,
    format_file_size,
    format_transfer_rate,
)
from moontransfer_android.android_runtime import (
    TransferNotification,
    parse_content_uri,
    post_transfer_result_notification,
    update_transfer_notification,
)
from moontransfer_android.receiver import (
    AndroidReceiveCallbacks,
    AndroidReceiveController,
)
from moontransfer_android.sender import (
    AndroidSendCallbacks,
    AndroidSendController,
)
from moontransfer_android.service_protocol import (
    RUNTIME_DIRECTORY_NAME,
    TransferServiceCommand,
    TransferServiceCommandName,
    TransferServiceOperation,
    TransferServiceRequest,
    TransferServiceStateStore,
    consume_service_commands,
    read_service_request,
    service_session_dir,
    staged_document_from_request,
)
from moontransfer_android.storage import cleanup_staged_document
from moontransfer_android.transport import (
    CrocProcessRunner,
    redact_sensitive_text,
    resolve_croc_executable,
)


SERVICE_POLL_SECONDS = 0.1
HEARTBEAT_SECONDS = 1.0
NOTIFICATION_PROGRESS_INTERVAL_SECONDS = 1.0

_SEND_PHASE_TEXT = {
    "preparing": "Preparazione e verifica del file...",
    "sending_metadata": "Invio delle informazioni sul file...",
    "awaiting_decision": "In attesa della decisione del destinatario...",
    "sending_file": "Trasferimento del file in corso...",
}
_RECEIVE_PHASE_TEXT = {
    "preparing": "Preparazione della ricezione...",
    "receiving_metadata": "Ricezione delle informazioni sul file...",
    "awaiting_decision": "In attesa della tua decisione...",
    "responding_to_decision": "Comunicazione della decisione...",
    "receiving_file": "Ricezione del file in corso...",
    "verifying": "Verifica di dimensione e hash SHA-256...",
    "awaiting_save": "File verificato. Tocca per scegliere dove salvarlo.",
    "saving": "Salvataggio nella destinazione scelta...",
}
_INDETERMINATE_STATES = frozenset(
    {
        "preparing",
        "sending_metadata",
        "receiving_metadata",
        "responding_to_decision",
        "verifying",
    }
)
_TRANSFER_STATES = frozenset({"sending_file", "receiving_file"})
_TERMINAL_STATES = frozenset(
    {"completed", "rejected", "cancelled", "failed"}
)


def build_transfer_notification(
    operation: TransferServiceOperation,
    state: str,
    *,
    filename: str | None = None,
    status: str = "",
    total_size: int | None = None,
    progress: TransferProgressSample | None = None,
    save_copied: int | None = None,
    save_total: int | None = None,
) -> TransferNotification:
    display_name = _notification_filename(filename)
    direction = (
        "Invio"
        if operation is TransferServiceOperation.SEND
        else "Ricezione"
    )
    title = f"{direction}: {display_name}" if display_name else direction

    terminal = build_transfer_result_notification(
        operation,
        state,
        filename=display_name,
    )
    if terminal is not None:
        return terminal
    if state == "cancelled":
        return TransferNotification(
            title="Trasferimento interrotto",
            text="Il trasferimento è stato interrotto.",
            public_text="Trasferimento MoonTransfer terminato",
        )

    if state in _TRANSFER_STATES:
        progress_text, progress_value = _format_transfer_progress(
            progress,
            total_size,
        )
        return TransferNotification(
            title=title,
            text=progress_text or _phase_text(operation, state, status),
            progress=progress_value,
            indeterminate=progress_value is None,
        )

    if state == "saving":
        progress_text, progress_value = _format_save_progress(
            save_copied,
            save_total,
        )
        return TransferNotification(
            title=title,
            text=progress_text or _phase_text(operation, state, status),
            progress=progress_value,
            indeterminate=progress_value is None,
        )

    return TransferNotification(
        title=title,
        text=_phase_text(operation, state, status),
        indeterminate=state in _INDETERMINATE_STATES,
    )


def build_transfer_result_notification(
    operation: TransferServiceOperation,
    state: str,
    *,
    filename: str | None = None,
) -> TransferNotification | None:
    if state not in _TERMINAL_STATES or state == "cancelled":
        return None

    display_name = _notification_filename(filename)
    if state == "completed":
        if operation is TransferServiceOperation.SEND:
            title = "Invio completato"
            text = (
                f"{display_name} è stato inviato correttamente."
                if display_name
                else "Il file è stato inviato correttamente."
            )
        else:
            title = "Ricezione completata"
            text = (
                f"{display_name} è stato salvato correttamente."
                if display_name
                else "Il file è stato salvato correttamente."
            )
    elif state == "rejected":
        title = "Trasferimento rifiutato"
        text = (
            "Il destinatario ha rifiutato il file."
            if operation is TransferServiceOperation.SEND
            else "Hai rifiutato il trasferimento."
        )
    else:
        title = "Trasferimento non riuscito"
        text = "Apri MoonTransfer per riprovare."

    return TransferNotification(
        title=title,
        text=text,
        public_text="Trasferimento MoonTransfer terminato",
    )


def _phase_text(
    operation: TransferServiceOperation,
    state: str,
    status: str,
) -> str:
    if status.startswith("Interruzione"):
        return status
    phases = (
        _SEND_PHASE_TEXT
        if operation is TransferServiceOperation.SEND
        else _RECEIVE_PHASE_TEXT
    )
    return phases.get(state, "Trasferimento in corso...")


def _format_transfer_progress(
    sample: TransferProgressSample | None,
    known_total: int | None,
) -> tuple[str | None, int | None]:
    if sample is None:
        return None, None

    total = sample.total_bytes or known_total
    transferred = sample.transferred_bytes
    progress = sample.percent
    if progress is None and total and transferred is not None:
        progress = round(transferred * 100 / total)
    if progress is not None:
        progress = max(0, min(100, progress))
    if transferred is None and total is not None and progress is not None:
        transferred = round(total * progress / 100)

    parts: list[str] = []
    if transferred is not None and total is not None:
        parts.append(
            f"{format_file_size(transferred)} / {format_file_size(total)}"
        )
    elif progress is not None:
        parts.append(f"{progress}%")

    if sample.speed_bps is not None and sample.speed_bps > 0:
        parts.append(format_transfer_rate(sample.speed_bps))
        if total is not None and transferred is not None:
            remaining = max(0, total - transferred) / sample.speed_bps
            parts.append(f"{format_duration(remaining)} rimanenti")

    return (" | ".join(parts) or None), progress


def _format_save_progress(
    copied: int | None,
    total: int | None,
) -> tuple[str | None, int | None]:
    if copied is None or total is None:
        return None, None
    progress = 100 if total == 0 else round(copied * 100 / total)
    progress = max(0, min(100, progress))
    return (
        f"Salvataggio: {format_file_size(copied)} / "
        f"{format_file_size(total)}",
        progress,
    )


def _notification_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    clean = " ".join(filename.split())
    if len(clean) <= 80:
        return clean
    return f"{clean[:77]}..."


class TransferServiceRuntime:
    def __init__(
        self,
        cache_root: Path,
        *,
        runner_factory: Callable[[], CrocProcessRunner] | None = None,
        uri_parser: Callable[[str], Any] = parse_content_uri,
        notification_updater: Callable[
            [TransferNotification], None
        ] = update_transfer_notification,
        result_notifier: Callable[
            [TransferNotification], None
        ] = post_transfer_result_notification,
        notification_clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cache_root = cache_root
        self.runner_factory = runner_factory or (
            lambda: CrocProcessRunner(resolve_croc_executable())
        )
        self.uri_parser = uri_parser
        self.notification_updater = notification_updater
        self.result_notifier = result_notifier
        self.notification_clock = notification_clock
        self.sleep = sleep
        self.request: TransferServiceRequest | None = None
        self.store: TransferServiceStateStore | None = None
        self.controller: AndroidSendController | AndroidReceiveController | None = None
        self._stopping = False
        self._notification_lock = Lock()
        self._notification_operation: TransferServiceOperation | None = None
        self._notification_state = "preparing"
        self._notification_status = "Preparazione del trasferimento..."
        self._notification_filename: str | None = None
        self._notification_total_size: int | None = None
        self._notification_progress: TransferProgressSample | None = None
        self._notification_save_copied: int | None = None
        self._notification_save_total: int | None = None
        self._last_notification_at: float | None = None
        self._last_notification: TransferNotification | None = None
        self._result_posted = False

    def run(self, session_id: str) -> None:
        request = read_service_request(self.cache_root, session_id)
        self.request = request
        store = TransferServiceStateStore(self.cache_root, request)
        self.store = store
        self._install_signal_handlers()
        self._initialize_notification(request)

        try:
            controller = self._create_controller(request, store)
            self.controller = controller
            self._notify(force=True)
            if request.operation is TransferServiceOperation.SEND:
                assert isinstance(controller, AndroidSendController)
                controller.start(staged_document_from_request(self.cache_root, request))
            else:
                assert isinstance(controller, AndroidReceiveController)
                if request.metadata_code is None:
                    raise RuntimeError("Codice di ricezione mancante.")
                controller.start(request.metadata_code)

            self._run_command_loop(controller, request, store)
            controller.wait()
        except BaseException as error:
            controller = self.controller
            if controller is not None and controller.active:
                controller.cancel()
                controller.wait(5)
            elif request.operation is TransferServiceOperation.SEND:
                try:
                    cleanup_staged_document(
                        staged_document_from_request(self.cache_root, request)
                    )
                except Exception:
                    pass
            store.update(
                state="failed",
                status=f"Trasferimento non completato: {error}",
                terminal=True,
            )
            self._set_notification_state(
                "failed",
                f"Trasferimento non completato: {error}",
            )
            self._notify(force=True)
            self._post_result_notification("failed")
        finally:
            store.update(service_done=True)

    def _create_controller(
        self,
        request: TransferServiceRequest,
        store: TransferServiceStateStore,
    ) -> AndroidSendController | AndroidReceiveController:
        runner = self.runner_factory()
        sessions_parent = (
            service_session_dir(self.cache_root, request.session_id)
            / RUNTIME_DIRECTORY_NAME
        )
        if request.operation is TransferServiceOperation.SEND:
            return AndroidSendController(
                runner=runner,
                sessions_parent=sessions_parent,
                callbacks=AndroidSendCallbacks(
                    on_state=lambda state: self._set_state(state.value),
                    on_status=lambda status: self._set_status(status),
                    on_prepared=lambda proposal, code: self._send_prepared(
                        proposal,
                        code,
                    ),
                    on_progress=self._set_progress,
                    on_finished=lambda state, message: self._finished(
                        state.value,
                        message,
                    ),
                ),
            )

        return AndroidReceiveController(
            runner=runner,
            sessions_parent=sessions_parent,
            callbacks=AndroidReceiveCallbacks(
                on_state=lambda state: self._set_state(state.value),
                on_status=lambda status: self._set_status(status),
                on_proposal=self._set_proposal,
                on_progress=self._set_progress,
                on_save_ready=self._set_proposal,
                on_save_progress=self._set_save_progress,
                on_finished=lambda state, message: self._finished(
                    state.value,
                    message,
                ),
            ),
        )

    def _run_command_loop(
        self,
        controller: AndroidSendController | AndroidReceiveController,
        request: TransferServiceRequest,
        store: TransferServiceStateStore,
    ) -> None:
        last_heartbeat = time.monotonic()
        while controller.active:
            try:
                commands = consume_service_commands(
                    self.cache_root,
                    request.session_id,
                )
                for command in commands:
                    self._dispatch_command(controller, request, command)
                if commands:
                    store.update(command_error=None)
            except Exception as error:
                store.update(command_error=str(error))

            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                store.heartbeat()
                last_heartbeat = now
            self.sleep(SERVICE_POLL_SECONDS)

    def _dispatch_command(
        self,
        controller: AndroidSendController | AndroidReceiveController,
        request: TransferServiceRequest,
        command: TransferServiceCommand,
    ) -> None:
        if command.command is TransferServiceCommandName.CANCEL:
            controller.cancel()
            return
        if request.operation is not TransferServiceOperation.RECEIVE:
            raise RuntimeError("Comando non valido durante un invio.")
        if not isinstance(controller, AndroidReceiveController):
            raise RuntimeError("Controller di ricezione non disponibile.")
        if command.command is TransferServiceCommandName.ACCEPT:
            controller.accept()
        elif command.command is TransferServiceCommandName.REJECT:
            controller.reject()
        elif command.command is TransferServiceCommandName.SAVE:
            if command.destination_uri is None:
                raise RuntimeError("Destinazione di salvataggio mancante.")
            controller.save_to_uri(self.uri_parser(command.destination_uri))
        else:
            raise RuntimeError("Comando del servizio non supportato.")

    def _send_prepared(self, proposal: Any, code: str) -> None:
        self._set_proposal(proposal)
        self._require_store().update(code=code)

    def _set_state(self, state: str) -> None:
        self._require_store().update(state=state)
        with self._notification_lock:
            self._notification_state = state
        self._notify(force=True)

    def _set_status(self, status: str) -> None:
        self._require_store().update(status=status)
        with self._notification_lock:
            self._notification_status = status
        self._notify(force=True)

    def _set_proposal(self, proposal: Any) -> None:
        self._require_store().set_proposal(proposal)
        with self._notification_lock:
            self._notification_filename = proposal.filename
            self._notification_total_size = proposal.size
        self._notify(force=True)

    def _set_progress(self, sample: TransferProgressSample) -> None:
        self._require_store().set_progress(sample)
        with self._notification_lock:
            self._notification_progress = sample
        self._notify(force=sample.percent == 100)

    def _set_save_progress(self, copied: int, total: int) -> None:
        self._require_store().set_save_progress(copied, total)
        with self._notification_lock:
            self._notification_save_copied = copied
            self._notification_save_total = total
        self._notify(force=copied == total)

    def _finished(self, state: str, message: str) -> None:
        self._require_store().update(
            state=state,
            status=message,
            terminal=True,
        )
        self._set_notification_state(state, message)
        self._notify(force=True)
        self._post_result_notification(state)

    def _initialize_notification(
        self,
        request: TransferServiceRequest,
    ) -> None:
        with self._notification_lock:
            self._notification_operation = request.operation
            self._notification_state = "preparing"
            self._notification_status = "Preparazione del trasferimento..."
            self._notification_filename = request.filename
            self._notification_total_size = request.size
            self._notification_progress = None
            self._notification_save_copied = None
            self._notification_save_total = None
            self._last_notification_at = None
            self._last_notification = None
            self._result_posted = False

    def _set_notification_state(self, state: str, status: str) -> None:
        with self._notification_lock:
            self._notification_state = state
            self._notification_status = status

    def _notify(self, *, force: bool = False) -> None:
        with self._notification_lock:
            operation = self._notification_operation
            if operation is None:
                return
            notification = build_transfer_notification(
                operation,
                self._notification_state,
                filename=self._notification_filename,
                status=self._notification_status,
                total_size=self._notification_total_size,
                progress=self._notification_progress,
                save_copied=self._notification_save_copied,
                save_total=self._notification_save_total,
            )
            if notification == self._last_notification:
                return
            now = self.notification_clock()
            if (
                not force
                and self._last_notification_at is not None
                and now - self._last_notification_at
                < NOTIFICATION_PROGRESS_INTERVAL_SECONDS
            ):
                return
            self._last_notification_at = now
            self._last_notification = notification

        try:
            self.notification_updater(notification)
        except Exception as error:
            self._report_notification_error("aggiornamento", error)

    def _post_result_notification(self, state: str) -> None:
        with self._notification_lock:
            operation = self._notification_operation
            if operation is None or self._result_posted:
                return
            notification = build_transfer_result_notification(
                operation,
                state,
                filename=self._notification_filename,
            )
            if notification is None:
                return
            self._result_posted = True

        try:
            self.result_notifier(notification)
        except Exception as error:
            self._report_notification_error("risultato", error)

    def _report_notification_error(
        self,
        action: str,
        error: Exception,
    ) -> None:
        request = self.request
        sensitive_values: tuple[str, ...] = ()
        if request is not None:
            sensitive_values = tuple(
                value
                for value in (
                    request.session_id,
                    request.metadata_code,
                    request.document_path,
                    request.filename,
                )
                if value
            )
        detail = redact_sensitive_text(str(error), sensitive_values)
        print(
            f"[notification] {action} non riuscito: "
            f"{type(error).__name__}: {detail}",
            flush=True,
        )

    def _install_signal_handlers(self) -> None:
        def stop(_signum: int, _frame: object) -> None:
            if self._stopping:
                return
            self._stopping = True
            controller = self.controller
            if controller is not None:
                controller.cancel()

        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(signum, stop)
            except (OSError, RuntimeError, ValueError):
                continue

    def _require_store(self) -> TransferServiceStateStore:
        if self.store is None:
            raise RuntimeError("Stato del servizio non disponibile.")
        return self.store

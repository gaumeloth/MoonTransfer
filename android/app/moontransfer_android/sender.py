from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Event, Lock, Thread

from moontransfer import croc
from moontransfer.cancellation import OperationCancelled
from moontransfer.files import CONTROL_METADATA_NAME
from moontransfer.payload import (
    SourcePayload,
    ensure_source_payload_unchanged,
    scan_source_payload,
)
from moontransfer.progress import (
    AggregateTransferProgress,
    TransferProgressSample,
    parse_transfer_progress,
)
from moontransfer.protocol import (
    TransferProposal,
    generate_croc_code,
    write_control_file,
)
from moontransfer_android.storage import (
    StagedDocument,
    StagedSelection,
    cleanup_staged_selection,
)
from moontransfer_android.transport import (
    CrocProcessResult,
    CrocProcessRunner,
    CrocProcessTimeout,
    croc_failure_detail,
)


CONTROL_IDLE_TIMEOUT_SECONDS = 15 * 60.0
REJECTION_TOKENS = ("declin", "reject", "refus", "cancel")


class AndroidSendState(Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    SENDING_METADATA = "sending_metadata"
    AWAITING_DECISION = "awaiting_decision"
    SENDING_FILE = "sending_file"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FAILED = "failed"


def _ignore(*_args: object) -> None:
    return None


@dataclass(frozen=True)
class AndroidSendCallbacks:
    on_state: Callable[[AndroidSendState], None] = _ignore
    on_status: Callable[[str], None] = _ignore
    on_prepared: Callable[[TransferProposal, str], None] = _ignore
    on_progress: Callable[[TransferProgressSample], None] = _ignore
    on_log: Callable[[str], None] = _ignore
    on_finished: Callable[[AndroidSendState, str], None] = _ignore


@dataclass
class AndroidSendSession:
    selection: StagedSelection
    root: Path | None = None
    metadata_croc_config: Path | None = None
    main_croc_config: Path | None = None
    metadata_path: Path | None = None
    payload: SourcePayload | None = None
    proposal: TransferProposal | None = None
    metadata_code: str | None = None
    rejected_by_receiver: bool = False


class AndroidSendController:
    def __init__(
        self,
        *,
        metadata_runner: CrocProcessRunner,
        main_runner: CrocProcessRunner,
        sessions_parent: Path,
        callbacks: AndroidSendCallbacks | None = None,
        idle_timeout: float = CONTROL_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self.metadata_runner = metadata_runner
        self.main_runner = main_runner
        self.sessions_parent = sessions_parent
        self.callbacks = callbacks or AndroidSendCallbacks()
        self.idle_timeout = idle_timeout
        self.state = AndroidSendState.IDLE
        self.session: AndroidSendSession | None = None
        self._cancel_requested = Event()
        self._lock = Lock()
        self._thread: Thread | None = None
        self._main_thread: Thread | None = None
        self._main_ready = Event()
        self._main_done = Event()
        self._main_stop_requested = Event()
        self._main_result: CrocProcessResult | None = None
        self._main_error: Exception | None = None
        self._progress = AggregateTransferProgress()

    @property
    def active(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, selection: StagedSelection | StagedDocument) -> None:
        if isinstance(selection, StagedDocument):
            selection = StagedSelection((selection,))
        with self._lock:
            if (
                self._thread is not None
                and self._thread.is_alive()
            ) or (
                self._main_thread is not None
                and self._main_thread.is_alive()
            ):
                raise RuntimeError("Un trasferimento è già in corso.")
            self._cancel_requested.clear()
            self._main_ready.clear()
            self._main_done.clear()
            self._main_stop_requested.clear()
            self._main_result = None
            self._main_error = None
            self.session = AndroidSendSession(selection=selection)
            thread = Thread(target=self._run, daemon=True)
            self._thread = thread

        self._set_state(AndroidSendState.PREPARING)
        self.callbacks.on_status(
            "Analisi dei file e calcolo degli hash SHA-256..."
        )
        thread.start()

    def cancel(self) -> None:
        with self._lock:
            main_active = (
                self._main_thread is not None
                and self._main_thread.is_alive()
            )
        if not self.active and not main_active:
            return
        self._cancel_requested.set()
        self.callbacks.on_status("Interruzione dell'invio in corso...")
        self.metadata_runner.request_stop()
        self.main_runner.request_stop()

    def wait(self, timeout: float | None = None) -> bool:
        with self._lock:
            thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _run(self) -> None:
        terminal_state = AndroidSendState.FAILED
        terminal_message = "Invio non completato."
        session = self._require_session()
        try:
            self._prepare_session(session)
            self._start_main_sender(session)
            self._wait_for_main_preparation()
            self._send_metadata(session)
            self._wait_for_main_transfer()
            if session.rejected_by_receiver:
                terminal_state = AndroidSendState.REJECTED
                terminal_message = "Trasferimento rifiutato dal destinatario."
            else:
                terminal_state = AndroidSendState.COMPLETED
                terminal_message = "Invio completato."
        except OperationCancelled:
            terminal_state = AndroidSendState.CANCELLED
            terminal_message = "Invio interrotto."
        except CrocProcessTimeout:
            terminal_message = (
                "Nessuna attività rilevata entro il tempo previsto. "
                "Il trasferimento è stato interrotto."
            )
        except Exception as error:
            terminal_message = f"Invio non completato: {error}"
        finally:
            self._stop_processes()
            self._cleanup_session(session)
            self._set_state(terminal_state)
            self.callbacks.on_status(terminal_message)
            self.callbacks.on_finished(terminal_state, terminal_message)
            with self._lock:
                self.session = None

    def _prepare_session(self, session: AndroidSendSession) -> None:
        self._raise_if_cancelled()
        payload = scan_source_payload(
            session.selection.root_paths,
            cancel_requested=self._cancel_requested.is_set,
        )
        proposal = payload.create_proposal()
        metadata_code = generate_croc_code()

        self.sessions_parent.mkdir(parents=True, exist_ok=True)
        root = Path(
            tempfile.mkdtemp(prefix="send-", dir=self.sessions_parent)
        )
        metadata_dir = root / "metadata-send"
        metadata_dir.mkdir()
        metadata_path = metadata_dir / CONTROL_METADATA_NAME
        metadata_croc_config = root / "metadata-croc-config"
        main_croc_config = root / "main-croc-config"
        write_control_file(metadata_path, proposal)

        session.root = root
        session.metadata_croc_config = metadata_croc_config
        session.main_croc_config = main_croc_config
        session.metadata_path = metadata_path
        session.payload = payload
        session.proposal = proposal
        session.metadata_code = metadata_code
        self._progress.reset(proposal.file_sizes)

    def _start_main_sender(self, session: AndroidSendSession) -> None:
        if (
            not session.payload
            or not session.proposal
            or not session.main_croc_config
            or not session.root
        ):
            raise RuntimeError("Sessione di invio principale incompleta.")

        self.callbacks.on_status(
            "Controllo dei file e preparazione del canale principale..."
        )
        ensure_source_payload_unchanged(
            session.payload,
            cancel_requested=self._cancel_requested.is_set,
        )
        self._raise_if_cancelled()

        thread = Thread(
            target=self._run_main_sender,
            args=(session,),
            daemon=True,
        )
        with self._lock:
            self._main_thread = thread
        thread.start()

    def _run_main_sender(self, session: AndroidSendSession) -> None:
        try:
            assert session.payload is not None
            assert session.proposal is not None
            assert session.main_croc_config is not None
            assert session.root is not None
            self._main_result = self.main_runner.run(
                croc.build_send_args(session.payload.root_paths),
                config_dir=session.main_croc_config,
                secret=session.proposal.main_code,
                workdir=session.root,
                idle_timeout=self.idle_timeout,
                cancel_requested=lambda: (
                    self._cancel_requested.is_set()
                    or self._main_stop_requested.is_set()
                ),
                on_line=lambda line: self._handle_process_line("main", line),
            )
        except Exception as error:
            self._main_error = error
        finally:
            self._main_done.set()

    def _wait_for_main_preparation(self) -> None:
        while not self._main_ready.wait(0.05):
            self._raise_if_cancelled()
            if self._main_done.is_set():
                self._raise_main_terminated(
                    "Preparazione del trasferimento principale"
                )

        self._raise_if_cancelled()
        if self._main_done.is_set():
            self._raise_main_terminated(
                "Preparazione del trasferimento principale"
            )

    def _send_metadata(self, session: AndroidSendSession) -> None:
        if not session.metadata_path or not session.metadata_croc_config:
            raise RuntimeError("Sessione metadati non inizializzata.")
        if not session.metadata_code or not session.proposal:
            raise RuntimeError("Codice metadati mancante.")

        self._set_state(AndroidSendState.SENDING_METADATA)
        self.callbacks.on_status(
            "Canale principale preparato. Avvio delle informazioni..."
        )
        code_published = False

        def handle_line(line: str) -> None:
            nonlocal code_published
            self._handle_process_line("metadata", line)
            if code_published or not croc.send_preparation_complete(line):
                return
            self._ensure_main_is_waiting()
            code_published = True
            self.callbacks.on_prepared(
                session.proposal,
                session.metadata_code,
            )
            self.callbacks.on_status(
                "Codice pronto. In attesa che il destinatario riceva "
                "le informazioni..."
            )

        result = self.metadata_runner.run(
            croc.build_send_args(session.metadata_path),
            config_dir=session.metadata_croc_config,
            secret=session.metadata_code,
            workdir=session.metadata_path.parent,
            idle_timeout=self.idle_timeout,
            cancel_requested=self._cancel_requested.is_set,
            on_line=handle_line,
            process_guard=self._ensure_main_is_waiting,
        )
        self._ensure_success(result, "Invio delle informazioni")
        if not code_published:
            raise RuntimeError(
                "croc ha terminato l'invio delle informazioni senza "
                "segnalare il completamento della preparazione."
            )

    def _wait_for_main_transfer(self) -> None:
        self._set_state(AndroidSendState.AWAITING_DECISION)
        self.callbacks.on_status(
            "Informazioni ricevute. Attendo la decisione del destinatario..."
        )
        while not self._main_done.wait(0.05):
            self._raise_if_cancelled()

        self._raise_if_cancelled()
        if self._main_error is not None:
            raise self._main_error
        result = self._main_result
        if result is None:
            raise RuntimeError("Risultato del processo principale mancante.")

        session = self._require_session()
        if session.rejected_by_receiver:
            return
        self._ensure_success(result, "Invio del contenuto")

    def _handle_process_line(self, role: str, line: str) -> None:
        self.callbacks.on_log(f"[{role}] {line}")
        if role != "main":
            return

        if croc.send_preparation_complete(line):
            self._main_ready.set()

        session = self._require_session()
        lowered = line.lower()
        if any(token in lowered for token in REJECTION_TOKENS):
            session.rejected_by_receiver = True

        sample = parse_transfer_progress(line)
        if "Sending (->" in line or sample is not None:
            if self.state == AndroidSendState.AWAITING_DECISION:
                self._set_state(AndroidSendState.SENDING_FILE)
                self.callbacks.on_status("Trasferimento dei file in corso...")
        if sample is not None:
            self.callbacks.on_progress(self._progress.apply(sample))

    def _ensure_main_is_waiting(self) -> None:
        self._raise_if_cancelled()
        if self._main_done.is_set():
            self._raise_main_terminated("Attesa della decisione")

    def _raise_main_terminated(self, action: str) -> None:
        self._raise_if_cancelled()
        if self._main_error is not None:
            raise self._main_error
        result = self._main_result
        if result is None:
            raise RuntimeError(
                f"{action}: il processo principale è terminato senza risultato."
            )
        if result.returncode != 0:
            detail = croc_failure_detail(result)
            raise RuntimeError(
                f"{action} non riuscita (exit code {result.returncode}): "
                f"{detail}"
            )
        raise RuntimeError(
            f"{action}: il processo principale è terminato prematuramente."
        )

    def _stop_processes(self) -> None:
        self._main_stop_requested.set()
        self.metadata_runner.request_stop()
        self.main_runner.request_stop()
        with self._lock:
            main_thread = self._main_thread
        if main_thread is not None and main_thread.is_alive():
            main_thread.join(5)

    @staticmethod
    def _ensure_success(result: CrocProcessResult, action: str) -> None:
        if result.returncode == 0:
            return
        detail = croc_failure_detail(result)
        raise RuntimeError(
            f"{action} non riuscito (exit code {result.returncode}): {detail}"
        )

    def _set_state(self, state: AndroidSendState) -> None:
        self.state = state
        self.callbacks.on_state(state)

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested.is_set():
            raise OperationCancelled

    def _require_session(self) -> AndroidSendSession:
        session = self.session
        if session is None:
            raise RuntimeError("Sessione di invio non disponibile.")
        return session

    @staticmethod
    def _cleanup_session(session: AndroidSendSession) -> None:
        if session.root is not None:
            shutil.rmtree(session.root, ignore_errors=True)
        cleanup_staged_selection(session.selection)

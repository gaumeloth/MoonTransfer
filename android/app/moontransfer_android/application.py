from __future__ import annotations

import time
from pathlib import Path
from threading import Event, Thread
from typing import Any

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import ListProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import ScreenManager
from kivy.uix.textinput import TextInput
from kivy.utils import platform

from moontransfer.cancellation import OperationCancelled
from moontransfer.build_info import CURRENT_BUILD
from moontransfer.progress import (
    TransferProgressSample,
    format_duration,
    format_file_size,
    format_transfer_rate,
)
from moontransfer.protocol import (
    PROTOCOL_VERSION,
    validate_croc_code,
)
from moontransfer.resources import APP_ICON_PATH
from moontransfer_android.app_state import (
    AndroidControlContext,
    ServiceSnapshotProjection,
    derive_android_control_state,
    project_service_snapshot,
)
from moontransfer_android.receiver import AndroidReceiveState
from moontransfer_android.sender import AndroidSendState
from moontransfer_android.service_client import (
    TransferServiceClient,
    TransferServiceHeartbeatMonitor,
    recover_latest_service_client,
    request_notification_permission,
)
from moontransfer_android.service_protocol import (
    TransferServiceError,
    TransferServiceOperation,
    TransferServiceSnapshot,
    TransferSummary,
)
from moontransfer_android.storage import (
    AndroidFilePicker,
    AndroidSavePicker,
    AndroidStorageError,
    StagedSelection,
    cleanup_staged_selection,
    cleanup_staging_parent,
    stage_document_uris,
)
from moontransfer_android.transport import (
    CrocProbeError,
    probe_croc,
)


TEXT_COLOR = (0.96, 0.96, 0.97, 1)
MUTED_COLOR = (0.71, 0.73, 0.78, 1)
SUCCESS_COLOR = (0.40, 0.82, 0.57, 1)
ERROR_COLOR = (0.95, 0.45, 0.45, 1)
ACCENT_COLOR = (0.20, 0.52, 0.88, 1)
SECONDARY_COLOR = (0.20, 0.22, 0.27, 1)
DESTRUCTIVE_COLOR = (0.67, 0.20, 0.24, 1)
CONFIRM_COLOR = (0.18, 0.50, 0.31, 1)
KV_PATH = Path(__file__).with_name("moontransfer.kv")
VIEW_IDS = (
    "build_info_button",
    "send_mode_button",
    "receive_mode_button",
    "view_manager",
    "transport_status",
    "probe_button",
    "select_button",
    "send_button",
    "cancel_button",
    "copy_button",
    "file_status",
    "send_status",
    "code_input",
    "progress_bar",
    "progress_details",
    "receive_code_input",
    "receive_start_button",
    "receive_proposal",
    "receive_accept_button",
    "receive_reject_button",
    "receive_save_button",
    "receive_cancel_button",
    "receive_progress_bar",
    "receive_progress_details",
    "receive_status",
)


class MoonWrappedLabel(Label):
    minimum_height = NumericProperty(dp(34))
    label_color = ListProperty(MUTED_COLOR)


class MoonActionButton(Button):
    button_color = ListProperty(ACCENT_COLOR)


class MoonTransferRoot(BoxLayout):
    pass


def _wrapped_label(
    text: str,
    *,
    font_size: float = 14,
    color: tuple[float, float, float, float] = MUTED_COLOR,
    minimum_height: float = 34,
) -> Label:
    return MoonWrappedLabel(
        text=text,
        label_color=color,
        font_size=sp(font_size),
        minimum_height=dp(minimum_height),
    )


def _button(
    text: str,
    *,
    color: tuple[float, float, float, float] = ACCENT_COLOR,
) -> Button:
    return MoonActionButton(
        text=text,
        button_color=color,
    )


class MoonTransferAndroidApp(App):
    title = "MoonTransfer"
    icon = str(APP_ICON_PATH)
    text_color = TEXT_COLOR
    muted_color = MUTED_COLOR
    accent_color = ACCENT_COLOR
    secondary_color = SECONDARY_COLOR
    destructive_color = DESTRUCTIVE_COLOR
    confirm_color = CONFIRM_COLOR
    build_subtitle = (
        f"Android {CURRENT_BUILD.version}\nProtocollo {PROTOCOL_VERSION}"
    )
    initial_transport_status = (
        "Trasporto croc: pronto per la verifica"
        if platform == "android"
        else "Trasporto croc: verifica disponibile nell'APK Android"
    )

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.transport_status: Label | None = None
        self.probe_button: Button | None = None
        self.select_button: Button | None = None
        self.send_button: Button | None = None
        self.cancel_button: Button | None = None
        self.copy_button: Button | None = None
        self.file_status: Label | None = None
        self.send_status: Label | None = None
        self.code_input: TextInput | None = None
        self.progress_bar: ProgressBar | None = None
        self.progress_details: Label | None = None

        self.receive_code_input: TextInput | None = None
        self.receive_start_button: Button | None = None
        self.receive_proposal: Label | None = None
        self.receive_accept_button: Button | None = None
        self.receive_reject_button: Button | None = None
        self.receive_save_button: Button | None = None
        self.receive_cancel_button: Button | None = None
        self.receive_progress_bar: ProgressBar | None = None
        self.receive_progress_details: Label | None = None
        self.receive_status: Label | None = None
        self.send_mode_button: Button | None = None
        self.receive_mode_button: Button | None = None
        self.build_info_button: Button | None = None

        self._picker: AndroidFilePicker | None = None
        self._save_picker: AndroidSavePicker | None = None
        self._selected_selection: StagedSelection | None = None
        self._service_client: TransferServiceClient | None = None
        self._service_heartbeat = TransferServiceHeartbeatMonitor()
        self._service_revision = -1
        self._service_snapshot_error: str | None = None
        self._service_command_error: str | None = None
        self._handled_terminal_session: str | None = None
        self._save_prompted_session: str | None = None
        self._service_available_after = 0.0
        self._service_release_event: Any = None
        self._send_state = AndroidSendState.IDLE
        self._receive_state = AndroidReceiveState.IDLE
        self._receive_proposal: TransferSummary | None = None
        self._transport_executable: Path | None = None
        self._staging_cancel = Event()
        self._staging = False
        self._probing = False
        self._closing = False
        self._code: str | None = None
        self._transfer_started_at: float | None = None
        self._receive_started_at: float | None = None
        self._view_manager: ScreenManager | None = None
        self._service_poll_event: Any = None

    @property
    def _cache_root(self) -> Path:
        return Path(self.user_data_dir) / "transfer-cache"

    @property
    def _staging_parent(self) -> Path:
        return self._cache_root / "staging"

    @property
    def _sessions_parent(self) -> Path:
        return self._cache_root / "sessions"

    def build(self) -> MoonTransferRoot:
        Window.clearcolor = (0.055, 0.059, 0.071, 1)
        root = Builder.load_file(str(KV_PATH))
        if not isinstance(root, MoonTransferRoot):
            raise RuntimeError(
                "Il layout Android non definisce una radice MoonTransferRoot."
            )
        self._bind_view(root)
        self._switch_mode("send")
        self._update_controls()
        return root

    def _bind_view(self, root: MoonTransferRoot) -> None:
        missing = sorted(set(VIEW_IDS).difference(root.ids))
        if missing:
            raise RuntimeError(
                "Il layout Android non contiene gli id richiesti: "
                + ", ".join(missing)
            )

        ids = root.ids
        self.build_info_button = ids["build_info_button"]
        self.send_mode_button = ids["send_mode_button"]
        self.receive_mode_button = ids["receive_mode_button"]
        self._view_manager = ids["view_manager"]
        self.transport_status = ids["transport_status"]
        self.probe_button = ids["probe_button"]
        self.select_button = ids["select_button"]
        self.send_button = ids["send_button"]
        self.cancel_button = ids["cancel_button"]
        self.copy_button = ids["copy_button"]
        self.file_status = ids["file_status"]
        self.send_status = ids["send_status"]
        self.code_input = ids["code_input"]
        self.progress_bar = ids["progress_bar"]
        self.progress_details = ids["progress_details"]
        self.receive_code_input = ids["receive_code_input"]
        self.receive_start_button = ids["receive_start_button"]
        self.receive_proposal = ids["receive_proposal"]
        self.receive_accept_button = ids["receive_accept_button"]
        self.receive_reject_button = ids["receive_reject_button"]
        self.receive_save_button = ids["receive_save_button"]
        self.receive_cancel_button = ids["receive_cancel_button"]
        self.receive_progress_bar = ids["receive_progress_bar"]
        self.receive_progress_details = ids["receive_progress_details"]
        self.receive_status = ids["receive_status"]

        self.build_info_button.bind(on_release=self._show_build_info)
        self.send_mode_button.bind(
            on_release=lambda _button: self._switch_mode("send")
        )
        self.receive_mode_button.bind(
            on_release=lambda _button: self._switch_mode("receive")
        )
        self.select_button.bind(on_release=self._open_file_picker)
        self.send_button.bind(on_release=self._start_send)
        self.copy_button.bind(on_release=self._copy_code)
        self.cancel_button.bind(on_release=self._cancel_send)
        self.probe_button.bind(on_release=self._start_transport_probe)
        self.receive_code_input.bind(
            text=lambda _widget, _value: self._update_controls()
        )
        self.receive_start_button.bind(on_release=self._start_receive)
        self.receive_reject_button.bind(on_release=self._reject_receive)
        self.receive_accept_button.bind(on_release=self._accept_receive)
        self.receive_save_button.bind(on_release=self._open_save_picker)
        self.receive_cancel_button.bind(on_release=self._cancel_receive)

    def _switch_mode(self, mode: str) -> None:
        manager = self._view_manager
        if manager is None or mode not in {"send", "receive"}:
            return
        manager.current = mode
        if self.send_mode_button is not None:
            self.send_mode_button.button_color = (
                ACCENT_COLOR if mode == "send" else SECONDARY_COLOR
            )
        if self.receive_mode_button is not None:
            self.receive_mode_button.button_color = (
                ACCENT_COLOR if mode == "receive" else SECONDARY_COLOR
            )

    def on_start(self) -> None:
        if platform != "android":
            return
        self._closing = False
        recovered_client: TransferServiceClient | None = None
        recovered_snapshot: TransferServiceSnapshot | None = None
        try:
            recovered_client, recovered_snapshot = recover_latest_service_client(
                self._cache_root
            )
        except TransferServiceError as error:
            self._show_error(
                "Ripristino trasferimento non riuscito",
                str(error),
            )

        service_active = bool(
            recovered_client is not None
            and (
                recovered_snapshot is None
                or not recovered_snapshot.service_done
            )
        )
        if not service_active:
            cleanup_staging_parent(self._staging_parent)
            cleanup_staging_parent(self._sessions_parent)
        try:
            self._picker = AndroidFilePicker()
        except AndroidStorageError as error:
            self._show_error("Selezione file non disponibile", str(error))
        try:
            self._save_picker = AndroidSavePicker()
        except AndroidStorageError as error:
            self._show_error("Salvataggio file non disponibile", str(error))
        request_notification_permission()
        self._service_poll_event = Clock.schedule_interval(
            self._poll_transfer_service,
            0.2,
        )
        if recovered_client is not None:
            if recovered_snapshot is None:
                self._attach_pending_service(recovered_client)
            else:
                self._attach_service(recovered_client, recovered_snapshot)
        if not service_active:
            self._start_transport_probe()

    def on_stop(self) -> None:
        self._closing = True
        self._staging_cancel.set()
        if self._service_poll_event is not None:
            self._service_poll_event.cancel()
            self._service_poll_event = None
        self._cancel_service_release_event()
        if self._picker is not None:
            self._picker.close()
            self._picker = None
        if self._save_picker is not None:
            self._save_picker.close()
            self._save_picker = None
        if self._service_client is None:
            cleanup_staged_selection(self._selected_selection)
        self._selected_selection = None

    def on_pause(self) -> bool:
        return True

    def on_resume(self) -> None:
        self._closing = False
        self._service_heartbeat.reset()
        self._update_controls()
        self._poll_transfer_service()

    def _start_transport_probe(self, *_args: object) -> None:
        if platform != "android" or self._probing:
            return
        self._probing = True
        self._transport_executable = None
        if self.transport_status is not None:
            self.transport_status.text = "Trasporto croc: verifica in corso..."
            self.transport_status.color = MUTED_COLOR
        self._update_controls()
        Thread(target=self._run_transport_probe, daemon=True).start()

    def _run_transport_probe(self) -> None:
        try:
            result = probe_croc(Path(self.user_data_dir) / "probe-croc-config")
            message = f"Trasporto croc disponibile (versione {result.version})"
            executable = result.executable
            success = True
        except CrocProbeError as error:
            message = f"Trasporto croc non disponibile: {error}"
            executable = None
            success = False
        self._post(self._finish_transport_probe, message, executable, success)

    def _finish_transport_probe(
        self,
        message: str,
        executable: Path | None,
        success: bool,
    ) -> None:
        self._probing = False
        self._transport_executable = executable
        if self.transport_status is not None:
            self.transport_status.text = message
            self.transport_status.color = SUCCESS_COLOR if success else ERROR_COLOR
        if (
            self.receive_status is not None
            and self._service_client is None
            and self._receive_state == AndroidReceiveState.IDLE
        ):
            self.receive_status.text = (
                "Trasporto disponibile. Inserisci il codice del mittente."
                if success
                else message
            )
            self.receive_status.color = SUCCESS_COLOR if success else ERROR_COLOR
        self._update_controls()

    def _open_file_picker(self, *_args: object) -> None:
        if self._picker is None:
            self._show_error(
                "Selezione file non disponibile",
                "Il selettore documenti Android non è disponibile.",
            )
            return
        try:
            self._picker.open(
                on_selected=self._stage_selected_uri,
                on_cancelled=self._selection_cancelled,
                on_error=lambda error: self._show_error(
                    "Selezione file non riuscita", str(error)
                ),
            )
            self._update_controls()
        except Exception as error:
            self._show_error("Selezione file non riuscita", str(error))
            self._update_controls()

    def _selection_cancelled(self) -> None:
        if self.send_status is not None and self._selected_selection is None:
            self.send_status.text = "Selezione annullata."
        self._update_controls()

    def _stage_selected_uri(self, uris: tuple[Any, ...]) -> None:
        self._staging_cancel.clear()
        self._staging = True
        if self.send_status is not None:
            self.send_status.text = "Copia dei file nell'area privata dell'app..."
            self.send_status.color = TEXT_COLOR
        self._update_controls()
        Thread(target=self._run_staging, args=(uris,), daemon=True).start()

    def _run_staging(self, uris: tuple[Any, ...]) -> None:
        try:
            selection = stage_document_uris(
                uris,
                self._staging_parent,
                cancel_requested=self._staging_cancel.is_set,
                on_progress=lambda copied, total: self._post(
                    self._show_staging_progress, copied, total
                ),
            )
        except OperationCancelled:
            self._post(self._finish_staging_cancelled)
        except Exception as error:
            self._post(self._finish_staging_error, str(error))
        else:
            self._post(self._finish_staging, selection)

    def _show_staging_progress(self, copied: int, total: int | None) -> None:
        if self.send_status is None:
            return
        if total is None:
            self.send_status.text = (
                f"Copia nell'area privata: {format_file_size(copied)}"
            )
        else:
            self.send_status.text = (
                "Copia nell'area privata: "
                f"{format_file_size(copied)} / {format_file_size(total)}"
            )

    def _finish_staging(self, selection: StagedSelection) -> None:
        self._staging = False
        if self._closing:
            cleanup_staged_selection(selection)
            return
        cleanup_staged_selection(self._selected_selection)
        self._selected_selection = selection
        if self.file_status is not None:
            if selection.count == 1:
                summary = selection.filenames[0]
            else:
                summary = f"{selection.count} file selezionati"
            self.file_status.text = (
                f"{summary}\n{format_file_size(selection.total_size)}"
            )
            self.file_status.color = TEXT_COLOR
        if self.send_status is not None:
            self.send_status.text = "File pronti per la preparazione."
            self.send_status.color = SUCCESS_COLOR
        self._update_controls()

    def _finish_staging_cancelled(self) -> None:
        self._staging = False
        if self.send_status is not None:
            self.send_status.text = "Copia dei file interrotta."
        self._update_controls()

    def _finish_staging_error(self, message: str) -> None:
        self._staging = False
        if self.send_status is not None:
            self.send_status.text = "Impossibile preparare i file selezionati."
            self.send_status.color = ERROR_COLOR
        self._show_error("Preparazione file non riuscita", message)
        self._update_controls()

    def _start_send(self, *_args: object) -> None:
        selection = self._selected_selection
        if (
            selection is None
            or self._transport_executable is None
            or self._service_is_releasing()
        ):
            self._update_controls()
            return

        self._code = None
        self._transfer_started_at = None
        if self.code_input is not None:
            self.code_input.text = ""
        if self.progress_bar is not None:
            self.progress_bar.value = 0
        if self.progress_details is not None:
            self.progress_details.text = (
                f"0 B / {format_file_size(selection.total_size)} | Velocità - | "
                "Trascorso - | Rimanente -"
            )

        try:
            client = TransferServiceClient.for_send(self._cache_root, selection)
            client.start()
        except Exception as error:
            self._show_error("Invio non avviato", str(error))
        else:
            self._selected_selection = None
            self._activate_service(client)
            self._poll_transfer_service()
        self._update_controls()

    def _cancel_send(self, *_args: object) -> None:
        client = self._service_client
        if client is None or client.operation is not TransferServiceOperation.SEND:
            return
        try:
            client.cancel()
            self._on_send_status("Richiesta di interruzione inviata...")
        except Exception as error:
            self._show_error("Interruzione non riuscita", str(error))

    def _on_send_state(self, state: AndroidSendState) -> None:
        previous = self._send_state
        self._send_state = state
        if state == AndroidSendState.SENDING_FILE:
            if previous != state or self._transfer_started_at is None:
                self._transfer_started_at = time.monotonic()
        self._update_controls()

    def _on_send_status(self, message: str) -> None:
        if self.send_status is not None:
            self.send_status.text = message
            self.send_status.color = TEXT_COLOR

    def _on_send_prepared(
        self,
        proposal: TransferSummary,
        code: str,
    ) -> None:
        code_changed = self._code != code
        self._code = code
        if self.file_status is not None:
            payload_label = (
                proposal.filename
                if proposal.is_single_file
                else f"{proposal.file_count} file in invio"
            )
            self.file_status.text = (
                f"{payload_label}\n{format_file_size(proposal.size)}"
            )
            self.file_status.color = TEXT_COLOR
        if self.code_input is not None:
            self.code_input.text = code
        if self.progress_details is not None:
            self.progress_details.text = (
                f"0 B / {format_file_size(proposal.size)} | Velocità - | "
                "Trascorso - | Rimanente -"
            )
        if code_changed:
            Clipboard.copy(code)
        self._update_controls()

    def _on_send_progress(self, sample: TransferProgressSample) -> None:
        percent = sample.percent or 0
        transferred = sample.transferred_bytes or 0
        total = sample.total_bytes
        if self.progress_bar is not None:
            self.progress_bar.value = percent

        elapsed = None
        if self._transfer_started_at is not None:
            elapsed = time.monotonic() - self._transfer_started_at
        remaining = None
        if (
            total is not None
            and sample.speed_bps is not None
            and sample.speed_bps > 0
        ):
            remaining = max(0, total - transferred) / sample.speed_bps

        if self.progress_details is not None:
            total_text = format_file_size(total) if total is not None else "-"
            self.progress_details.text = (
                f"{format_file_size(transferred)} / {total_text} | "
                f"Velocità {format_transfer_rate(sample.speed_bps)} | "
                f"Trascorso {format_duration(elapsed)} | "
                f"Rimanente {format_duration(remaining)}"
            )

    def _on_send_finished(
        self,
        state: AndroidSendState,
        message: str,
    ) -> None:
        self._send_state = state
        self._selected_selection = None
        self._code = None
        if self.file_status is not None:
            self.file_status.text = "Nessun file selezionato."
            self.file_status.color = MUTED_COLOR
        if self.code_input is not None:
            self.code_input.text = ""
        if self.send_status is not None:
            self.send_status.text = message
            self.send_status.color = (
                SUCCESS_COLOR
                if state == AndroidSendState.COMPLETED
                else MUTED_COLOR
                if state in {AndroidSendState.CANCELLED, AndroidSendState.REJECTED}
                else ERROR_COLOR
            )
        if state == AndroidSendState.COMPLETED and self.progress_bar is not None:
            self.progress_bar.value = 100
        if state == AndroidSendState.FAILED:
            self._show_error("Invio non riuscito", message)
        self._update_controls()

    def _start_receive(self, *_args: object) -> None:
        code_input = self.receive_code_input
        if (
            self._transport_executable is None
            or code_input is None
            or self._service_is_releasing()
        ):
            self._update_controls()
            return

        code = code_input.text.strip()
        try:
            validate_croc_code(code)
        except Exception as error:
            self._show_error("Codice non valido", str(error))
            return

        self._receive_proposal = None
        self._receive_started_at = None
        if self.receive_proposal is not None:
            self.receive_proposal.text = "Attendo le informazioni sul contenuto..."
            self.receive_proposal.color = MUTED_COLOR
        if self.receive_progress_bar is not None:
            self.receive_progress_bar.value = 0
        if self.receive_progress_details is not None:
            self.receive_progress_details.text = (
                "0 B / - | Velocità - | Trascorso - | Rimanente -"
            )

        try:
            client = TransferServiceClient.for_receive(self._cache_root, code)
            client.start()
        except Exception as error:
            self._show_error("Ricezione non avviata", str(error))
        else:
            self._activate_service(client)
            self._poll_transfer_service()
        self._update_controls()

    def _accept_receive(self, *_args: object) -> None:
        client = self._receive_service_client()
        if client is None:
            return
        try:
            client.accept()
            self._on_receive_state(
                AndroidReceiveState.RESPONDING_TO_DECISION
            )
            self._on_receive_status("Decisione inviata al servizio...")
        except Exception as error:
            self._show_error("Decisione non applicata", str(error))
        self._update_controls()

    def _reject_receive(self, *_args: object) -> None:
        client = self._receive_service_client()
        if client is None:
            return
        try:
            client.reject()
            self._on_receive_state(
                AndroidReceiveState.RESPONDING_TO_DECISION
            )
            self._on_receive_status("Decisione inviata al servizio...")
        except Exception as error:
            self._show_error("Decisione non applicata", str(error))
        self._update_controls()

    def _cancel_receive(self, *_args: object) -> None:
        client = self._receive_service_client()
        if client is None:
            return
        try:
            client.cancel()
            self._on_receive_status("Richiesta di interruzione inviata...")
        except Exception as error:
            self._show_error("Interruzione non riuscita", str(error))

    def _on_receive_state(self, state: AndroidReceiveState) -> None:
        previous = self._receive_state
        self._receive_state = state
        if state == AndroidReceiveState.RECEIVING_FILE:
            if previous != state or self._receive_started_at is None:
                self._receive_started_at = time.monotonic()
        self._update_controls()

    def _on_receive_status(self, message: str) -> None:
        if self.receive_status is not None:
            self.receive_status.text = message
            self.receive_status.color = TEXT_COLOR

    def _on_receive_proposal(self, proposal: TransferSummary) -> None:
        self._receive_proposal = proposal
        if self.receive_proposal is not None:
            if proposal.is_single_file:
                hash_text = proposal.sha256 or "non disponibile"
                summary = (
                    f"Nome: {proposal.filename}\n"
                    f"Dimensione: {format_file_size(proposal.size)}\n"
                    f"SHA-256: {hash_text}"
                )
            else:
                roots = proposal.roots or (proposal.filename,)
                visible_roots = ", ".join(roots[:3])
                if len(roots) > 3:
                    visible_roots += f", ... (+{len(roots) - 3})"
                counts = f"File: {proposal.file_count}"
                if proposal.directory_count:
                    counts += f" | Cartelle: {proposal.directory_count}"
                summary = (
                    f"{counts}\n"
                    f"Dimensione totale: {format_file_size(proposal.size)}\n"
                    f"Contenuto: {visible_roots}\n"
                    "SHA-256: incluso per ogni file"
                )
            self.receive_proposal.text = summary
            self.receive_proposal.color = TEXT_COLOR
        if self.receive_progress_details is not None:
            self.receive_progress_details.text = (
                f"0 B / {format_file_size(proposal.size)} | Velocità - | "
                "Trascorso - | Rimanente -"
            )
        self._update_controls()

    def _on_receive_progress(self, sample: TransferProgressSample) -> None:
        percent = sample.percent or 0
        transferred = sample.transferred_bytes or 0
        total = sample.total_bytes
        if self.receive_progress_bar is not None:
            self.receive_progress_bar.value = percent

        elapsed = None
        if self._receive_started_at is not None:
            elapsed = time.monotonic() - self._receive_started_at
        remaining = None
        if (
            total is not None
            and sample.speed_bps is not None
            and sample.speed_bps > 0
        ):
            remaining = max(0, total - transferred) / sample.speed_bps

        if self.receive_progress_details is not None:
            total_text = format_file_size(total) if total is not None else "-"
            self.receive_progress_details.text = (
                f"{format_file_size(transferred)} / {total_text} | "
                f"Velocità {format_transfer_rate(sample.speed_bps)} | "
                f"Trascorso {format_duration(elapsed)} | "
                f"Rimanente {format_duration(remaining)}"
            )

    def _on_receive_save_ready(self, proposal: TransferSummary) -> None:
        self._receive_proposal = proposal
        if self.receive_progress_bar is not None:
            self.receive_progress_bar.value = 100
        self._update_controls()
        if self._save_picker is not None and not self._closing:
            self._open_save_picker()

    def _open_save_picker(self, *_args: object) -> None:
        picker = self._save_picker
        proposal = self._receive_proposal
        client = self._receive_service_client()
        if picker is None or proposal is None or client is None:
            self._show_error(
                "Salvataggio non disponibile",
                "Il selettore di destinazione Android non è disponibile.",
            )
            return
        if self._receive_state != AndroidReceiveState.AWAITING_SAVE:
            return
        try:
            picker.open(
                proposal.filename if proposal.is_single_file else None,
                select_directory=not proposal.is_single_file,
                on_selected=self._save_destination_selected,
                on_cancelled=self._save_destination_cancelled,
                on_error=self._save_destination_error,
            )
        except Exception as error:
            self._save_destination_error(error)
        self._update_controls()

    def _save_destination_selected(self, uri: Any) -> None:
        client = self._receive_service_client()
        if client is None:
            return
        try:
            client.save_to_uri(str(uri.toString()))
            self._on_receive_state(AndroidReceiveState.SAVING)
            self._on_receive_status(
                "Destinazione inviata al servizio di trasferimento..."
            )
        except Exception as error:
            self._save_destination_error(error)
        self._update_controls()

    def _save_destination_cancelled(self) -> None:
        if self.receive_status is not None:
            self.receive_status.text = (
                "Salvataggio annullato. Il contenuto verificato resta disponibile "
                "finché il trasferimento non viene interrotto."
            )
            self.receive_status.color = MUTED_COLOR
        self._update_controls()

    def _save_destination_error(self, error: Exception) -> None:
        self._show_error("Destinazione non disponibile", str(error))
        self._update_controls()

    def _on_receive_save_progress(self, copied: int, total: int) -> None:
        percent = (copied * 100 / total) if total else 100
        if self.receive_progress_bar is not None:
            self.receive_progress_bar.value = percent
        if self.receive_progress_details is not None:
            self.receive_progress_details.text = (
                f"Salvataggio: {format_file_size(copied)} / "
                f"{format_file_size(total)}"
            )

    def _on_receive_finished(
        self,
        state: AndroidReceiveState,
        message: str,
    ) -> None:
        self._receive_state = state
        if self.receive_code_input is not None:
            self.receive_code_input.text = ""
        if self.receive_status is not None:
            self.receive_status.text = message
            self.receive_status.color = (
                SUCCESS_COLOR
                if state == AndroidReceiveState.COMPLETED
                else MUTED_COLOR
                if state
                in {AndroidReceiveState.CANCELLED, AndroidReceiveState.REJECTED}
                else ERROR_COLOR
            )
        if (
            state == AndroidReceiveState.COMPLETED
            and self.receive_progress_bar is not None
        ):
            self.receive_progress_bar.value = 100
        if state == AndroidReceiveState.FAILED:
            self._show_error("Ricezione non riuscita", message)
        self._update_controls()

    def _activate_service(self, client: TransferServiceClient) -> None:
        self._cancel_service_release_event()
        self._service_heartbeat.reset()
        self._service_client = client
        self._service_revision = -1
        self._service_snapshot_error = None
        self._service_command_error = None
        self._handled_terminal_session = None
        self._save_prompted_session = None
        self._service_available_after = 0.0
        if client.operation is TransferServiceOperation.SEND:
            self._send_state = AndroidSendState.PREPARING
            self._receive_state = AndroidReceiveState.IDLE
            self._switch_mode("send")
        else:
            self._send_state = AndroidSendState.IDLE
            self._receive_state = AndroidReceiveState.PREPARING
            self._switch_mode("receive")
        self._update_controls()

    def _attach_pending_service(self, client: TransferServiceClient) -> None:
        self._activate_service(client)
        message = "Riconnessione al servizio di trasferimento in corso..."
        if client.operation is TransferServiceOperation.SEND:
            self._on_send_status(message)
        else:
            self._on_receive_status(message)
        self._poll_transfer_service()

    def _attach_service(
        self,
        client: TransferServiceClient,
        snapshot: TransferServiceSnapshot,
    ) -> None:
        self._activate_service(client)
        try:
            projection = project_service_snapshot(
                snapshot,
                expected_operation=client.operation,
            )
        except TransferServiceError as error:
            self._handle_unresponsive_service(
                client,
                message=(
                    "Lo stato salvato del servizio non è valido. "
                    "La sessione incompleta è stata rimossa; avvia un nuovo "
                    f"trasferimento. Dettaglio: {error}"
                ),
            )
            return
        self._service_heartbeat.timed_out(snapshot)
        self._apply_service_snapshot(snapshot, projection)
        if snapshot.service_done:
            self._release_service(client)

    def _poll_transfer_service(self, *_args: object) -> None:
        client = self._service_client
        if client is None:
            self._update_controls()
            return
        try:
            snapshot = client.snapshot()
            projection = project_service_snapshot(
                snapshot,
                expected_operation=client.operation,
            )
        except TransferServiceError as error:
            detail = str(error)
            if self._service_snapshot_error != detail:
                self._service_snapshot_error = detail
                print(
                    f"[service] stato temporaneamente non disponibile: {detail}",
                    flush=True,
                )
            if self._service_heartbeat.snapshot_unavailable_timed_out():
                self._handle_unresponsive_service(
                    client,
                    message=(
                        "Lo stato del servizio è rimasto non leggibile. "
                        "La sessione incompleta è stata rimossa; avvia un "
                        f"nuovo trasferimento. Dettaglio: {detail}"
                    ),
                )
            return

        self._service_snapshot_error = None
        if self._service_heartbeat.timed_out(snapshot):
            self._handle_unresponsive_service(
                client,
                snapshot=snapshot,
                projection=projection,
                message=(
                    "Il servizio di trasferimento non risponde. "
                    "La sessione incompleta è stata rimossa; avvia un nuovo "
                    "trasferimento."
                ),
            )
            return

        if snapshot.revision != self._service_revision:
            self._service_revision = snapshot.revision
            self._apply_service_snapshot(snapshot, projection)

        if snapshot.command_error != self._service_command_error:
            self._service_command_error = snapshot.command_error
            if snapshot.command_error:
                self._show_error(
                    "Comando non applicato",
                    snapshot.command_error,
                )

        if snapshot.service_done:
            self._release_service(client)

    def _handle_unresponsive_service(
        self,
        client: TransferServiceClient,
        *,
        message: str,
        snapshot: TransferServiceSnapshot | None = None,
        projection: ServiceSnapshotProjection | None = None,
    ) -> None:
        if self._service_client is not client:
            return

        if snapshot is not None and projection is not None and snapshot.terminal:
            if snapshot.revision != self._service_revision:
                self._service_revision = snapshot.revision
                self._apply_service_snapshot(snapshot, projection)
        else:
            if client.operation is TransferServiceOperation.SEND:
                self._on_send_finished(AndroidSendState.FAILED, message)
            else:
                self._on_receive_finished(AndroidReceiveState.FAILED, message)

        try:
            client.stop()
        except Exception as error:
            print(
                "[service] arresto forzato non riuscito: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
        self._release_service(client)
        cleanup_staging_parent(self._staging_parent)
        cleanup_staging_parent(self._sessions_parent)

    def _apply_service_snapshot(
        self,
        snapshot: TransferServiceSnapshot,
        projection: ServiceSnapshotProjection,
    ) -> None:
        if projection.operation is TransferServiceOperation.SEND:
            state = projection.state
            if not isinstance(state, AndroidSendState):
                raise TransferServiceError(
                    "Proiezione dello stato di invio non valida."
                )
            self._switch_mode(projection.mode)
            self._on_send_state(state)
            self._on_send_status(snapshot.status)
            if snapshot.proposal is not None and snapshot.code is not None:
                self._on_send_prepared(snapshot.proposal, snapshot.code)
            if snapshot.progress is not None:
                self._on_send_progress(snapshot.progress)
            if (
                snapshot.terminal
                and self._handled_terminal_session != snapshot.session_id
            ):
                self._handled_terminal_session = snapshot.session_id
                self._on_send_finished(state, snapshot.status)
            return

        state = projection.state
        if not isinstance(state, AndroidReceiveState):
            raise TransferServiceError(
                "Proiezione dello stato di ricezione non valida."
            )
        self._switch_mode(projection.mode)
        self._on_receive_state(state)
        self._on_receive_status(snapshot.status)
        if snapshot.proposal is not None:
            self._on_receive_proposal(snapshot.proposal)
        if snapshot.progress is not None:
            self._on_receive_progress(snapshot.progress)
        if snapshot.save_copied is not None and snapshot.save_total is not None:
            self._on_receive_save_progress(
                snapshot.save_copied,
                snapshot.save_total,
            )
        if (
            state == AndroidReceiveState.AWAITING_SAVE
            and snapshot.proposal is not None
            and self._save_prompted_session != snapshot.session_id
        ):
            self._save_prompted_session = snapshot.session_id
            self._on_receive_save_ready(snapshot.proposal)
        if (
            snapshot.terminal
            and self._handled_terminal_session != snapshot.session_id
        ):
            self._handled_terminal_session = snapshot.session_id
            self._on_receive_finished(state, snapshot.status)

    def _release_service(self, client: TransferServiceClient) -> None:
        if self._service_client is not client:
            return
        try:
            client.cleanup()
        except TransferServiceError:
            pass
        self._service_client = None
        self._service_heartbeat.reset()
        self._service_revision = -1
        self._service_snapshot_error = None
        self._cancel_service_release_event()
        self._service_available_after = time.monotonic() + 1.0
        self._service_release_event = Clock.schedule_once(
            self._finish_service_release,
            1.0,
        )
        if self._transport_executable is None and not self._probing:
            self._start_transport_probe()
        self._update_controls()

    def _finish_service_release(self, *_args: object) -> None:
        self._service_release_event = None
        self._service_available_after = 0.0
        self._update_controls()

    def _cancel_service_release_event(self) -> None:
        event = self._service_release_event
        self._service_release_event = None
        if event is not None:
            event.cancel()

    def _service_is_releasing(self) -> bool:
        available_after = self._service_available_after
        if available_after <= 0:
            return False
        if time.monotonic() < available_after:
            return True

        self._cancel_service_release_event()
        self._service_available_after = 0.0
        return False

    def _receive_service_client(self) -> TransferServiceClient | None:
        client = self._service_client
        if client is None or client.operation is not TransferServiceOperation.RECEIVE:
            return None
        return client

    def _copy_code(self, *_args: object) -> None:
        if not self._code:
            return
        Clipboard.copy(self._code)
        if self.send_status is not None:
            self.send_status.text = "Codice copiato negli appunti."

    def _show_build_info(self, *_args: object) -> None:
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )
        diagnostics = CURRENT_BUILD.diagnostics()
        details = TextInput(
            text=diagnostics,
            readonly=True,
            multiline=True,
            font_size=sp(13),
        )
        content.add_widget(details)

        actions = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(48),
        )
        copy_button = _button("Copia diagnostica", color=SECONDARY_COLOR)
        close_button = _button("Chiudi")
        actions.add_widget(copy_button)
        actions.add_widget(close_button)
        content.add_widget(actions)

        popup = Popup(
            title="Informazioni su MoonTransfer",
            content=content,
            size_hint=(0.92, None),
            height=dp(390),
            auto_dismiss=True,
        )
        copy_button.bind(
            on_release=lambda _button: Clipboard.copy(diagnostics)
        )
        close_button.bind(on_release=lambda _button: popup.dismiss())
        popup.open()

    def _update_controls(self) -> None:
        picker_pending = bool(self._picker and self._picker.pending)
        save_picker_pending = bool(
            self._save_picker and self._save_picker.pending
        )
        service_operation = (
            self._service_client.operation
            if self._service_client is not None
            else None
        )
        controls = derive_android_control_state(
            AndroidControlContext(
                is_android=platform == "android",
                send_state=self._send_state,
                receive_state=self._receive_state,
                service_operation=service_operation,
                service_releasing=self._service_is_releasing(),
                has_selected_document=self._selected_selection is not None,
                transport_available=self._transport_executable is not None,
                staging=self._staging,
                file_picker_pending=picker_pending,
                save_picker_available=self._save_picker is not None,
                save_picker_pending=save_picker_pending,
                probing=self._probing,
                send_code_available=self._code is not None,
                receive_code_valid=self._receive_code_is_valid(),
            )
        )
        if self.select_button is not None:
            self.select_button.disabled = not controls.select_file
        if self.send_button is not None:
            self.send_button.disabled = not controls.start_send
        if self.cancel_button is not None:
            self.cancel_button.disabled = not controls.cancel_send
        if self.copy_button is not None:
            self.copy_button.disabled = not controls.copy_code
        if self.receive_code_input is not None:
            self.receive_code_input.disabled = not controls.edit_receive_code
        if self.receive_start_button is not None:
            self.receive_start_button.disabled = not controls.start_receive
        if self.receive_accept_button is not None:
            self.receive_accept_button.disabled = not controls.accept_receive
        if self.receive_reject_button is not None:
            self.receive_reject_button.disabled = not controls.reject_receive
        if self.receive_save_button is not None:
            self.receive_save_button.disabled = not controls.save_receive
        if self.receive_cancel_button is not None:
            self.receive_cancel_button.disabled = not controls.cancel_receive
        if self.probe_button is not None:
            self.probe_button.disabled = not controls.probe_transport

    def _receive_code_is_valid(self) -> bool:
        if self.receive_code_input is None:
            return False
        try:
            validate_croc_code(self.receive_code_input.text.strip())
        except Exception:
            return False
        return True

    def _show_error(self, title: str, message: str) -> None:
        content = _wrapped_label(
            message,
            color=TEXT_COLOR,
            minimum_height=80,
        )
        Popup(
            title=title,
            content=content,
            size_hint=(0.9, None),
            height=dp(250),
            auto_dismiss=True,
        ).open()

    @staticmethod
    def _post(callback: Any, *args: object) -> None:
        Clock.schedule_once(lambda _dt: callback(*args))


def main() -> None:
    MoonTransferAndroidApp().run()

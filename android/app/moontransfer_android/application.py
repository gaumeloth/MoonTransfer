from __future__ import annotations

import time
from pathlib import Path
from threading import Event, Thread
from typing import Any

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
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
    StagedDocument,
    cleanup_staged_document,
    cleanup_staging_parent,
    stage_document_uri,
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


def _wrapped_label(
    text: str,
    *,
    font_size: float = 14,
    color: tuple[float, float, float, float] = MUTED_COLOR,
    minimum_height: float = 34,
) -> Label:
    label = Label(
        text=text,
        color=color,
        font_size=sp(font_size),
        halign="left",
        valign="middle",
        size_hint_y=None,
        height=dp(minimum_height),
    )
    label.bind(
        width=lambda widget, value: setattr(widget, "text_size", (value, None))
    )
    label.bind(
        texture_size=lambda widget, value: setattr(
            widget,
            "height",
            max(dp(minimum_height), value[1] + dp(8)),
        )
    )
    return label


def _button(
    text: str,
    *,
    color: tuple[float, float, float, float] = ACCENT_COLOR,
) -> Button:
    return Button(
        text=text,
        size_hint_y=None,
        height=dp(48),
        background_normal="",
        background_down="",
        background_color=color,
        color=TEXT_COLOR,
        font_size=sp(15),
    )


class MoonTransferAndroidApp(App):
    title = "MoonTransfer"
    icon = str(APP_ICON_PATH)

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
        self._selected_document: StagedDocument | None = None
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
        self._view_container: BoxLayout | None = None
        self._send_view: ScrollView | None = None
        self._receive_view: ScrollView | None = None
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

    def build(self) -> BoxLayout:
        Window.clearcolor = (0.055, 0.059, 0.071, 1)

        root = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=(dp(20), dp(18), dp(20), dp(12)),
        )
        header = BoxLayout(
            orientation="horizontal",
            spacing=dp(12),
            size_hint_y=None,
            height=dp(82),
        )
        header.add_widget(
            Image(
                source=str(APP_ICON_PATH),
                size_hint=(None, None),
                size=(dp(72), dp(72)),
                fit_mode="contain",
            )
        )
        title_box = BoxLayout(orientation="vertical")
        title_box.add_widget(
            _wrapped_label(
                "MoonTransfer",
                font_size=25,
                color=TEXT_COLOR,
                minimum_height=38,
            )
        )
        title_box.add_widget(
            _wrapped_label(
                (
                    f"Android {CURRENT_BUILD.version}\n"
                    f"Protocollo {PROTOCOL_VERSION}"
                ),
                minimum_height=40,
            )
        )
        header.add_widget(title_box)
        self.build_info_button = _button("i", color=SECONDARY_COLOR)
        self.build_info_button.size_hint = (None, None)
        self.build_info_button.size = (dp(42), dp(42))
        self.build_info_button.font_size = sp(20)
        self.build_info_button.bind(on_release=self._show_build_info)
        header.add_widget(self.build_info_button)
        root.add_widget(header)

        mode_row = BoxLayout(
            orientation="horizontal",
            spacing=dp(2),
            size_hint_y=None,
            height=dp(46),
        )
        self.send_mode_button = _button("Invia")
        self.send_mode_button.height = dp(46)
        self.send_mode_button.bind(
            on_release=lambda _button: self._switch_mode("send")
        )
        mode_row.add_widget(self.send_mode_button)
        self.receive_mode_button = _button("Ricevi", color=SECONDARY_COLOR)
        self.receive_mode_button.height = dp(46)
        self.receive_mode_button.bind(
            on_release=lambda _button: self._switch_mode("receive")
        )
        mode_row.add_widget(self.receive_mode_button)
        root.add_widget(mode_row)

        self._send_view = self._build_send_view()
        self._receive_view = self._build_receive_view()
        self._view_container = BoxLayout()
        root.add_widget(self._view_container)
        self._switch_mode("send")

        self._update_controls()
        return root

    def _switch_mode(self, mode: str) -> None:
        container = self._view_container
        if container is None:
            return
        target = self._send_view if mode == "send" else self._receive_view
        if target is None:
            return
        container.clear_widgets()
        container.add_widget(target)
        if self.send_mode_button is not None:
            self.send_mode_button.background_color = (
                ACCENT_COLOR if mode == "send" else SECONDARY_COLOR
            )
        if self.receive_mode_button is not None:
            self.receive_mode_button.background_color = (
                ACCENT_COLOR if mode == "receive" else SECONDARY_COLOR
            )

    def _build_send_view(self) -> ScrollView:
        scroll = ScrollView(do_scroll_x=False)
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=(0, dp(12), 0, dp(24)),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        content.add_widget(
            _wrapped_label(
                "Invia un file a MoonTransfer su un altro dispositivo.",
                font_size=16,
                color=TEXT_COLOR,
                minimum_height=40,
            )
        )

        self.select_button = _button("Seleziona file")
        self.select_button.bind(on_release=self._open_file_picker)
        content.add_widget(self.select_button)

        self.file_status = _wrapped_label("Nessun file selezionato.")
        content.add_widget(self.file_status)

        self.send_button = _button("Prepara e invia")
        self.send_button.bind(on_release=self._start_send)
        content.add_widget(self.send_button)

        content.add_widget(
            _wrapped_label(
                "Codice da comunicare al destinatario",
                color=TEXT_COLOR,
                minimum_height=30,
            )
        )
        code_row = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(48),
        )
        self.code_input = TextInput(
            readonly=True,
            multiline=False,
            hint_text="Il codice apparirà durante la preparazione",
            size_hint=(1, None),
            height=dp(48),
            font_size=sp(14),
        )
        code_row.add_widget(self.code_input)
        self.copy_button = _button("Copia", color=SECONDARY_COLOR)
        self.copy_button.size_hint_x = None
        self.copy_button.width = dp(88)
        self.copy_button.bind(on_release=self._copy_code)
        code_row.add_widget(self.copy_button)
        content.add_widget(code_row)

        self.progress_bar = ProgressBar(
            max=100,
            value=0,
            size_hint_y=None,
            height=dp(18),
        )
        content.add_widget(self.progress_bar)
        self.progress_details = _wrapped_label(
            "0 B / - | Velocità - | Trascorso - | Rimanente -",
            minimum_height=38,
        )
        content.add_widget(self.progress_details)

        self.send_status = _wrapped_label(
            "Seleziona un file per iniziare.",
            color=TEXT_COLOR,
            minimum_height=44,
        )
        content.add_widget(self.send_status)

        self.cancel_button = _button("Interrompi", color=(0.67, 0.20, 0.24, 1))
        self.cancel_button.bind(on_release=self._cancel_send)
        content.add_widget(self.cancel_button)

        self.transport_status = _wrapped_label(
            (
                "Trasporto croc: pronto per la verifica"
                if platform == "android"
                else "Trasporto croc: verifica disponibile nell'APK Android"
            ),
            minimum_height=38,
        )
        content.add_widget(self.transport_status)
        self.probe_button = _button("Verifica trasporto", color=SECONDARY_COLOR)
        self.probe_button.bind(on_release=self._start_transport_probe)
        content.add_widget(self.probe_button)

        scroll.add_widget(content)
        return scroll

    def _build_receive_view(self) -> ScrollView:
        scroll = ScrollView(do_scroll_x=False)
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=(0, dp(12), 0, dp(24)),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        content.add_widget(
            _wrapped_label(
                "Ricevi un file inviato da MoonTransfer.",
                font_size=16,
                color=TEXT_COLOR,
                minimum_height=40,
            )
        )
        content.add_widget(
            _wrapped_label(
                "Codice comunicato dal mittente",
                color=TEXT_COLOR,
                minimum_height=30,
            )
        )
        self.receive_code_input = TextInput(
            multiline=False,
            hint_text="Codice di trasferimento",
            size_hint_y=None,
            height=dp(48),
            font_size=sp(14),
        )
        self.receive_code_input.bind(
            text=lambda _widget, _value: self._update_controls()
        )
        content.add_widget(self.receive_code_input)

        self.receive_start_button = _button("Ricevi informazioni")
        self.receive_start_button.bind(on_release=self._start_receive)
        content.add_widget(self.receive_start_button)

        self.receive_proposal = _wrapped_label(
            "Nessuna proposta ricevuta.",
            minimum_height=72,
        )
        content.add_widget(self.receive_proposal)

        decision_row = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(48),
        )
        self.receive_reject_button = _button(
            "Rifiuta",
            color=(0.67, 0.20, 0.24, 1),
        )
        self.receive_reject_button.bind(on_release=self._reject_receive)
        decision_row.add_widget(self.receive_reject_button)
        self.receive_accept_button = _button(
            "Accetta",
            color=(0.18, 0.50, 0.31, 1),
        )
        self.receive_accept_button.bind(on_release=self._accept_receive)
        decision_row.add_widget(self.receive_accept_button)
        content.add_widget(decision_row)

        self.receive_progress_bar = ProgressBar(
            max=100,
            value=0,
            size_hint_y=None,
            height=dp(18),
        )
        content.add_widget(self.receive_progress_bar)
        self.receive_progress_details = _wrapped_label(
            "0 B / - | Velocità - | Trascorso - | Rimanente -",
            minimum_height=38,
        )
        content.add_widget(self.receive_progress_details)

        self.receive_status = _wrapped_label(
            "Inserisci il codice per ricevere le informazioni sul file.",
            color=TEXT_COLOR,
            minimum_height=52,
        )
        content.add_widget(self.receive_status)

        self.receive_save_button = _button("Scegli dove salvare")
        self.receive_save_button.bind(on_release=self._open_save_picker)
        content.add_widget(self.receive_save_button)

        self.receive_cancel_button = _button(
            "Interrompi",
            color=(0.67, 0.20, 0.24, 1),
        )
        self.receive_cancel_button.bind(on_release=self._cancel_receive)
        content.add_widget(self.receive_cancel_button)

        scroll.add_widget(content)
        return scroll

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
            cleanup_staged_document(self._selected_document)
        self._selected_document = None

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
        if self.send_status is not None and self._selected_document is None:
            self.send_status.text = "Selezione annullata."
        self._update_controls()

    def _stage_selected_uri(self, uri: Any) -> None:
        self._staging_cancel.clear()
        self._staging = True
        if self.send_status is not None:
            self.send_status.text = "Copia del file nell'area privata dell'app..."
            self.send_status.color = TEXT_COLOR
        self._update_controls()
        Thread(target=self._run_staging, args=(uri,), daemon=True).start()

    def _run_staging(self, uri: Any) -> None:
        try:
            document = stage_document_uri(
                uri,
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
            self._post(self._finish_staging, document)

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

    def _finish_staging(self, document: StagedDocument) -> None:
        self._staging = False
        if self._closing:
            cleanup_staged_document(document)
            return
        cleanup_staged_document(self._selected_document)
        self._selected_document = document
        if self.file_status is not None:
            self.file_status.text = (
                f"{document.filename}\n{format_file_size(document.size)}"
            )
            self.file_status.color = TEXT_COLOR
        if self.send_status is not None:
            self.send_status.text = "File pronto per la preparazione."
            self.send_status.color = SUCCESS_COLOR
        self._update_controls()

    def _finish_staging_cancelled(self) -> None:
        self._staging = False
        if self.send_status is not None:
            self.send_status.text = "Copia del file interrotta."
        self._update_controls()

    def _finish_staging_error(self, message: str) -> None:
        self._staging = False
        if self.send_status is not None:
            self.send_status.text = "Impossibile preparare il file selezionato."
            self.send_status.color = ERROR_COLOR
        self._show_error("Preparazione file non riuscita", message)
        self._update_controls()

    def _start_send(self, *_args: object) -> None:
        document = self._selected_document
        if (
            document is None
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
                f"0 B / {format_file_size(document.size)} | Velocità - | "
                "Trascorso - | Rimanente -"
            )

        try:
            client = TransferServiceClient.for_send(self._cache_root, document)
            client.start()
        except Exception as error:
            self._show_error("Invio non avviato", str(error))
        else:
            self._selected_document = None
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
        self._selected_document = None
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
            self.receive_proposal.text = "Attendo le informazioni sul file..."
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
        hash_text = proposal.sha256 or "non disponibile per questo contenuto"
        if self.receive_proposal is not None:
            self.receive_proposal.text = (
                f"Nome: {proposal.filename}\n"
                f"Dimensione: {format_file_size(proposal.size)}\n"
                f"SHA-256: {hash_text}"
            )
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
                proposal.filename,
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
                "Salvataggio annullato. Il file verificato resta disponibile "
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
                has_selected_document=self._selected_document is not None,
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

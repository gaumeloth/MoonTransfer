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
from moontransfer.progress import (
    TransferProgressSample,
    format_duration,
    format_file_size,
    format_transfer_rate,
)
from moontransfer.protocol import PROTOCOL_VERSION, TransferProposal
from moontransfer.resources import APP_ICON_PATH
from moontransfer_android.sender import (
    AndroidSendCallbacks,
    AndroidSendController,
    AndroidSendState,
)
from moontransfer_android.storage import (
    AndroidFilePicker,
    AndroidStorageError,
    StagedDocument,
    cleanup_staged_document,
    cleanup_staging_parent,
    stage_document_uri,
)
from moontransfer_android.transport import (
    CrocProbeError,
    CrocProcessRunner,
    probe_croc,
)


TEXT_COLOR = (0.96, 0.96, 0.97, 1)
MUTED_COLOR = (0.71, 0.73, 0.78, 1)
SUCCESS_COLOR = (0.40, 0.82, 0.57, 1)
ERROR_COLOR = (0.95, 0.45, 0.45, 1)
ACCENT_COLOR = (0.20, 0.52, 0.88, 1)
SECONDARY_COLOR = (0.20, 0.22, 0.27, 1)
ACTIVE_SEND_STATES = frozenset(
    {
        AndroidSendState.PREPARING,
        AndroidSendState.SENDING_METADATA,
        AndroidSendState.AWAITING_DECISION,
        AndroidSendState.SENDING_FILE,
    }
)


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

        self._picker: AndroidFilePicker | None = None
        self._selected_document: StagedDocument | None = None
        self._controller: AndroidSendController | None = None
        self._transport_executable: Path | None = None
        self._staging_cancel = Event()
        self._staging = False
        self._probing = False
        self._closing = False
        self._code: str | None = None
        self._transfer_started_at: float | None = None

    @property
    def _cache_root(self) -> Path:
        return Path(self.user_data_dir) / "transfer-cache"

    @property
    def _staging_parent(self) -> Path:
        return self._cache_root / "staging"

    @property
    def _sessions_parent(self) -> Path:
        return self._cache_root / "sessions"

    def build(self) -> ScrollView:
        Window.clearcolor = (0.055, 0.059, 0.071, 1)

        scroll = ScrollView(do_scroll_x=False)
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=(dp(20), dp(18), dp(20), dp(24)),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        header = BoxLayout(
            orientation="horizontal",
            spacing=dp(12),
            size_hint_y=None,
            height=dp(72),
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
                f"Android | Protocollo {PROTOCOL_VERSION}",
                minimum_height=28,
            )
        )
        header.add_widget(title_box)
        content.add_widget(header)

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
        self._update_controls()
        return scroll

    def on_start(self) -> None:
        if platform != "android":
            return
        cleanup_staging_parent(self._staging_parent)
        cleanup_staging_parent(self._sessions_parent)
        try:
            self._picker = AndroidFilePicker()
        except AndroidStorageError as error:
            self._show_error("Selezione file non disponibile", str(error))
        self._start_transport_probe()

    def on_stop(self) -> None:
        self._closing = True
        self._staging_cancel.set()
        if self._picker is not None:
            self._picker.close()
            self._picker = None
        if self._controller is not None and self._controller.active:
            self._controller.cancel()
        else:
            cleanup_staged_document(self._selected_document)
        self._selected_document = None

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
        executable = self._transport_executable
        if document is None or executable is None:
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

        callbacks = AndroidSendCallbacks(
            on_state=lambda state: self._post(self._on_send_state, state),
            on_status=lambda message: self._post(self._on_send_status, message),
            on_prepared=lambda proposal, code: self._post(
                self._on_send_prepared, proposal, code
            ),
            on_progress=lambda sample: self._post(
                self._on_send_progress, sample
            ),
            on_finished=lambda state, message: self._post(
                self._on_send_finished, state, message
            ),
        )
        controller = AndroidSendController(
            runner=CrocProcessRunner(executable),
            sessions_parent=self._sessions_parent,
            callbacks=callbacks,
        )
        self._controller = controller
        try:
            controller.start(document)
        except Exception as error:
            self._controller = None
            self._show_error("Invio non avviato", str(error))
        self._update_controls()

    def _cancel_send(self, *_args: object) -> None:
        if self._controller is not None:
            self._controller.cancel()

    def _on_send_state(self, state: AndroidSendState) -> None:
        if state == AndroidSendState.SENDING_FILE:
            self._transfer_started_at = time.monotonic()
        self._update_controls()

    def _on_send_status(self, message: str) -> None:
        if self.send_status is not None:
            self.send_status.text = message
            self.send_status.color = TEXT_COLOR

    def _on_send_prepared(
        self,
        proposal: TransferProposal,
        code: str,
    ) -> None:
        self._code = code
        if self.code_input is not None:
            self.code_input.text = code
        if self.progress_details is not None:
            self.progress_details.text = (
                f"0 B / {format_file_size(proposal.size)} | Velocità - | "
                "Trascorso - | Rimanente -"
            )
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
        self._selected_document = None
        self._controller = None
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

    def _copy_code(self, *_args: object) -> None:
        if not self._code:
            return
        Clipboard.copy(self._code)
        if self.send_status is not None:
            self.send_status.text = "Codice copiato negli appunti."

    def _update_controls(self) -> None:
        transfer_active = bool(
            self._controller
            and self._controller.state in ACTIVE_SEND_STATES
        )
        picker_pending = bool(self._picker and self._picker.pending)
        if self.select_button is not None:
            self.select_button.disabled = (
                platform != "android"
                or self._staging
                or transfer_active
                or picker_pending
            )
        if self.send_button is not None:
            self.send_button.disabled = (
                self._selected_document is None
                or self._transport_executable is None
                or self._staging
                or transfer_active
            )
        if self.cancel_button is not None:
            self.cancel_button.disabled = not transfer_active
        if self.copy_button is not None:
            self.copy_button.disabled = self._code is None
        if self.probe_button is not None:
            self.probe_button.disabled = (
                platform != "android" or self._probing or transfer_active
            )

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

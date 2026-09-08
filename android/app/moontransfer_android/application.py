from __future__ import annotations

import time
from pathlib import Path
from threading import Event, Thread
from typing import Any

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.uix.recycleview import RecycleView
from kivy.uix.screenmanager import ScreenManager
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
    AndroidControlState,
    ServiceSnapshotProjection,
    derive_android_control_state,
    project_service_snapshot,
)
from moontransfer_android.receiver import AndroidReceiveState
from moontransfer_android.sharing import (
    AndroidShareError,
    SharedDirectoryAccessError,
    codes_from_shared_text,
    read_shared_intent,
    share_code,
    stage_shared_uris,
)
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
    cleanup_staged_document,
    cleanup_staged_selection,
    cleanup_staging_parent,
    stage_directory_uri,
    stage_document_uris,
)
from moontransfer_android.transport import (
    CrocProbeError,
    probe_croc,
)
from moontransfer_android import theme
from moontransfer_android.ui_state import (
    receive_result_tone,
    receive_view_stage,
    send_result_tone,
    send_view_stage,
)
from moontransfer_android.widgets import (
    MoonButton,
    MoonDialogOverlay,
    MoonIconButton,
    MoonMetric,
    MoonNavButton,
    MoonProgressBar,
    MoonResultPanel,
    MoonSnackbar,
    MoonTextInput,
    MoonTransferRoot,
    MoonWrappedLabel,
)


TEXT_COLOR = theme.TEXT
MUTED_COLOR = theme.TEXT_MUTED
SUCCESS_COLOR = theme.SUCCESS
ERROR_COLOR = theme.ERROR
ACCENT_COLOR = theme.PRIMARY
SECONDARY_COLOR = theme.SURFACE_STRONG
DESTRUCTIVE_COLOR = theme.ERROR_SOFT
CONFIRM_COLOR = theme.SUCCESS_SOFT
KV_PATH = Path(__file__).with_name("moontransfer.kv")
VIEW_IDS = (
    "build_info_button",
    "send_mode_button",
    "receive_mode_button",
    "view_manager",
    "transport_panel",
    "transport_status",
    "probe_button",
    "send_stage_manager",
    "select_button",
    "select_directory_button",
    "clear_selection_button",
    "selection_list",
    "send_button",
    "cancel_button",
    "copy_button",
    "share_button",
    "file_status",
    "send_status",
    "code_input",
    "progress_bar",
    "progress_details",
    "send_waiting_title",
    "send_payload_summary",
    "send_transfer_summary",
    "send_percent",
    "send_speed_metric",
    "send_remaining_metric",
    "send_elapsed_metric",
    "send_transferred_metric",
    "transfer_cancel_button",
    "send_result_panel",
    "send_reset_button",
    "receive_stage_manager",
    "receive_code_input",
    "receive_paste_button",
    "receive_start_button",
    "receive_loading_cancel_button",
    "receive_proposal",
    "receive_accept_button",
    "receive_reject_button",
    "receive_save_button",
    "receive_cancel_button",
    "receive_progress_bar",
    "receive_progress_details",
    "receive_transfer_summary",
    "receive_percent",
    "receive_speed_metric",
    "receive_remaining_metric",
    "receive_elapsed_metric",
    "receive_transferred_metric",
    "receive_save_summary",
    "receive_save_progress_bar",
    "receive_save_progress_details",
    "receive_save_cancel_button",
    "receive_result_panel",
    "receive_reset_button",
    "receive_status",
    "snackbar",
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
        self.transport_panel: Any = None
        self.transport_status: MoonWrappedLabel | None = None
        self.probe_button: MoonButton | None = None
        self.select_button: MoonButton | None = None
        self.select_directory_button: MoonButton | None = None
        self.clear_selection_button: MoonButton | None = None
        self.selection_list: RecycleView | None = None
        self.send_button: MoonButton | None = None
        self.cancel_button: MoonButton | None = None
        self.transfer_cancel_button: MoonButton | None = None
        self.copy_button: MoonIconButton | None = None
        self.share_button: MoonButton | None = None
        self.file_status: MoonWrappedLabel | None = None
        self.send_status: MoonWrappedLabel | None = None
        self.code_input: MoonTextInput | None = None
        self.progress_bar: MoonProgressBar | None = None
        self.progress_details: MoonWrappedLabel | None = None
        self.send_waiting_title: MoonWrappedLabel | None = None
        self.send_payload_summary: MoonWrappedLabel | None = None
        self.send_transfer_summary: MoonWrappedLabel | None = None
        self.send_percent: MoonWrappedLabel | None = None
        self.send_speed_metric: MoonMetric | None = None
        self.send_remaining_metric: MoonMetric | None = None
        self.send_elapsed_metric: MoonMetric | None = None
        self.send_transferred_metric: MoonMetric | None = None
        self.send_result_panel: MoonResultPanel | None = None
        self.send_reset_button: MoonButton | None = None

        self.receive_code_input: MoonTextInput | None = None
        self.receive_paste_button: MoonIconButton | None = None
        self.receive_start_button: MoonButton | None = None
        self.receive_loading_cancel_button: MoonButton | None = None
        self.receive_proposal: MoonWrappedLabel | None = None
        self.receive_accept_button: MoonButton | None = None
        self.receive_reject_button: MoonButton | None = None
        self.receive_save_button: MoonButton | None = None
        self.receive_cancel_button: MoonButton | None = None
        self.receive_progress_bar: MoonProgressBar | None = None
        self.receive_progress_details: MoonWrappedLabel | None = None
        self.receive_transfer_summary: MoonWrappedLabel | None = None
        self.receive_percent: MoonWrappedLabel | None = None
        self.receive_speed_metric: MoonMetric | None = None
        self.receive_remaining_metric: MoonMetric | None = None
        self.receive_elapsed_metric: MoonMetric | None = None
        self.receive_transferred_metric: MoonMetric | None = None
        self.receive_save_summary: MoonWrappedLabel | None = None
        self.receive_save_progress_bar: MoonProgressBar | None = None
        self.receive_save_progress_details: MoonWrappedLabel | None = None
        self.receive_save_cancel_button: MoonButton | None = None
        self.receive_result_panel: MoonResultPanel | None = None
        self.receive_reset_button: MoonButton | None = None
        self.receive_status: MoonWrappedLabel | None = None
        self.send_mode_button: MoonNavButton | None = None
        self.receive_mode_button: MoonNavButton | None = None
        self.build_info_button: MoonIconButton | None = None
        self.snackbar: MoonSnackbar | None = None

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
        self._send_stage_manager: ScreenManager | None = None
        self._receive_stage_manager: ScreenManager | None = None
        self._service_poll_event: Any = None
        self._share_poll_event: Any = None
        self._share_activity: Any = None
        self._snackbar_event: Any = None
        self._dialog_overlay: MoonDialogOverlay | None = None

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
        Window.clearcolor = theme.BACKGROUND
        root = Builder.load_file(str(KV_PATH))
        if not isinstance(root, MoonTransferRoot):
            raise RuntimeError(
                "Il layout Android non definisce una radice MoonTransferRoot."
            )
        self._bind_view(root)
        self._switch_mode("send")
        self._update_stage_views()
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
        self.transport_panel = ids["transport_panel"]
        self.transport_status = ids["transport_status"]
        self.probe_button = ids["probe_button"]
        self._send_stage_manager = ids["send_stage_manager"]
        self.select_button = ids["select_button"]
        self.select_directory_button = ids["select_directory_button"]
        self.clear_selection_button = ids["clear_selection_button"]
        self.selection_list = ids["selection_list"]
        self.send_button = ids["send_button"]
        self.cancel_button = ids["cancel_button"]
        self.copy_button = ids["copy_button"]
        self.share_button = ids["share_button"]
        self.file_status = ids["file_status"]
        self.send_status = ids["send_status"]
        self.code_input = ids["code_input"]
        self.progress_bar = ids["progress_bar"]
        self.progress_details = ids["progress_details"]
        self.send_waiting_title = ids["send_waiting_title"]
        self.send_payload_summary = ids["send_payload_summary"]
        self.send_transfer_summary = ids["send_transfer_summary"]
        self.send_percent = ids["send_percent"]
        self.send_speed_metric = ids["send_speed_metric"]
        self.send_remaining_metric = ids["send_remaining_metric"]
        self.send_elapsed_metric = ids["send_elapsed_metric"]
        self.send_transferred_metric = ids["send_transferred_metric"]
        self.transfer_cancel_button = ids["transfer_cancel_button"]
        self.send_result_panel = ids["send_result_panel"]
        self.send_reset_button = ids["send_reset_button"]
        self._receive_stage_manager = ids["receive_stage_manager"]
        self.receive_code_input = ids["receive_code_input"]
        self.receive_paste_button = ids["receive_paste_button"]
        self.receive_start_button = ids["receive_start_button"]
        self.receive_loading_cancel_button = ids["receive_loading_cancel_button"]
        self.receive_proposal = ids["receive_proposal"]
        self.receive_accept_button = ids["receive_accept_button"]
        self.receive_reject_button = ids["receive_reject_button"]
        self.receive_save_button = ids["receive_save_button"]
        self.receive_cancel_button = ids["receive_cancel_button"]
        self.receive_progress_bar = ids["receive_progress_bar"]
        self.receive_progress_details = ids["receive_progress_details"]
        self.receive_transfer_summary = ids["receive_transfer_summary"]
        self.receive_percent = ids["receive_percent"]
        self.receive_speed_metric = ids["receive_speed_metric"]
        self.receive_remaining_metric = ids["receive_remaining_metric"]
        self.receive_elapsed_metric = ids["receive_elapsed_metric"]
        self.receive_transferred_metric = ids["receive_transferred_metric"]
        self.receive_save_summary = ids["receive_save_summary"]
        self.receive_save_progress_bar = ids["receive_save_progress_bar"]
        self.receive_save_progress_details = ids["receive_save_progress_details"]
        self.receive_save_cancel_button = ids["receive_save_cancel_button"]
        self.receive_result_panel = ids["receive_result_panel"]
        self.receive_reset_button = ids["receive_reset_button"]
        self.receive_status = ids["receive_status"]
        self.snackbar = ids["snackbar"]

        self.build_info_button.bind(on_release=self._show_build_info)
        self.send_mode_button.bind(
            on_release=lambda _button: self._switch_mode("send")
        )
        self.receive_mode_button.bind(
            on_release=lambda _button: self._switch_mode("receive")
        )
        self.select_button.bind(on_release=self._open_file_picker)
        self.select_directory_button.bind(
            on_release=self._open_directory_picker
        )
        self.clear_selection_button.bind(on_release=self._clear_selection)
        self.send_button.bind(on_release=self._start_send)
        self.copy_button.bind(on_release=self._copy_code)
        self.share_button.bind(on_release=self._share_code)
        self.cancel_button.bind(on_release=self._cancel_send)
        self.transfer_cancel_button.bind(on_release=self._cancel_send)
        self.send_reset_button.bind(on_release=self._reset_send_view)
        self.probe_button.bind(on_release=self._start_transport_probe)
        self.receive_code_input.bind(
            text=self._on_receive_code_changed
        )
        self.receive_paste_button.bind(on_release=self._paste_receive_code)
        self.receive_start_button.bind(on_release=self._start_receive)
        self.receive_loading_cancel_button.bind(on_release=self._cancel_receive)
        self.receive_reject_button.bind(on_release=self._reject_receive)
        self.receive_accept_button.bind(on_release=self._accept_receive)
        self.receive_save_button.bind(on_release=self._open_save_picker)
        self.receive_cancel_button.bind(on_release=self._cancel_receive)
        self.receive_save_cancel_button.bind(on_release=self._cancel_receive)
        self.receive_reset_button.bind(on_release=self._reset_receive_view)
        self._refresh_selection_view()

    def _switch_mode(self, mode: str) -> None:
        manager = self._view_manager
        if manager is None or mode not in {"send", "receive"}:
            return
        manager.current = mode
        if self.send_mode_button is not None:
            self.send_mode_button.selected = mode == "send"
        if self.receive_mode_button is not None:
            self.receive_mode_button.selected = mode == "receive"

    def _update_stage_views(self) -> None:
        if self._send_stage_manager is not None:
            self._send_stage_manager.current = send_view_stage(
                self._send_state
            ).value
        if self._receive_stage_manager is not None:
            self._receive_stage_manager.current = receive_view_stage(
                self._receive_state
            ).value

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

        try:
            from jnius import autoclass, cast
            self._share_activity = cast(
                "io.github.gaumeloth.moontransfer.MoonTransferActivity",
                autoclass("org.kivy.android.PythonActivity").mActivity,
            )
            self._share_poll_event = Clock.schedule_interval(self._poll_shared_intents, 0.2)
        except Exception:
            self._show_error("Condivisione non disponibile", "Impossibile attivare le condivisioni Android.")

    def on_stop(self) -> None:
        self._closing = True
        if self._share_poll_event is not None:
            self._share_poll_event.cancel()
            self._share_poll_event = None
        self._share_activity = None
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
        self._set_transport_panel_visible(True)
        if self.transport_status is not None:
            self.transport_status.text = "Trasporto croc: verifica in corso..."
            self.transport_status.label_color = theme.WARNING
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
            self.transport_status.label_color = (
                SUCCESS_COLOR if success else ERROR_COLOR
            )
        self._set_transport_panel_visible(not success)
        if success:
            self._show_snackbar("Trasporto croc pronto")
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
            self.receive_status.label_color = (
                SUCCESS_COLOR if success else ERROR_COLOR
            )
        self._update_controls()

    def _set_transport_panel_visible(self, visible: bool) -> None:
        panel = self.transport_panel
        if panel is None:
            return
        Animation.cancel_all(panel, "height", "opacity")
        panel.disabled = not visible
        Animation(
            height=dp(58) if visible else 0,
            opacity=1 if visible else 0,
            duration=0.16,
        ).start(panel)

    def _open_file_picker(self, *_args: object) -> None:
        self._open_source_picker(select_directory=False)

    def _open_directory_picker(self, *_args: object) -> None:
        self._open_source_picker(select_directory=True)

    def _open_source_picker(self, *, select_directory: bool) -> None:
        if self._picker is None:
            self._show_error(
                "Selezione non disponibile",
                "Il selettore documenti Android non è disponibile.",
            )
            return
        element_label = "cartella" if select_directory else "file"
        try:
            self._picker.open(
                select_directory=select_directory,
                on_selected=lambda uris: self._stage_selected_uri(
                    uris,
                    is_directory=select_directory,
                ),
                on_cancelled=self._selection_cancelled,
                on_error=lambda error: self._show_error(
                    f"Selezione {element_label} non riuscita", str(error)
                ),
            )
            self._update_controls()
        except Exception as error:
            self._show_error(
                f"Selezione {element_label} non riuscita",
                str(error),
            )
            self._update_controls()

    def _selection_cancelled(self) -> None:
        if self.send_status is not None and self._selected_selection is None:
            self.send_status.text = "Selezione annullata."
        self._update_controls()

    def _stage_selected_uri(
        self,
        uris: tuple[Any, ...],
        *,
        is_directory: bool,
        shared: bool = False,
    ) -> None:
        self._staging_cancel.clear()
        self._staging = True
        existing_selection = self._selected_selection
        if self.send_status is not None:
            self.send_status.text = (
                "Aggiunta del contenuto nell'area privata dell'app..."
                if existing_selection is not None
                else "Copia del contenuto nell'area privata dell'app..."
            )
            self.send_status.label_color = TEXT_COLOR
        self._update_controls()
        Thread(
            target=self._run_staging,
            args=(uris, existing_selection, is_directory, shared),
            daemon=True,
        ).start()

    def _run_staging(
        self,
        uris: tuple[Any, ...],
        existing_selection: StagedSelection | None,
        is_directory: bool,
        shared: bool = False,
    ) -> None:
        try:
            def progress(copied: int, total: int | None) -> None:
                self._post(self._show_staging_progress, copied, total)

            if shared:
                selection = stage_shared_uris(
                    uris, self._staging_parent,
                    existing_selection=existing_selection,
                    cancel_requested=self._staging_cancel.is_set,
                    on_progress=progress,
                )
            elif is_directory:
                if len(uris) != 1:
                    raise AndroidStorageError(
                        "Android non ha restituito una sola cartella."
                    )
                document = stage_directory_uri(
                    uris[0],
                    self._staging_parent,
                    existing_selection=existing_selection,
                    cancel_requested=self._staging_cancel.is_set,
                    on_progress=progress,
                )
                selection = StagedSelection((document,))
            else:
                selection = stage_document_uris(
                    uris,
                    self._staging_parent,
                    existing_selection=existing_selection,
                    cancel_requested=self._staging_cancel.is_set,
                    on_progress=progress,
                )
        except OperationCancelled:
            self._post(self._finish_staging_cancelled)
        except SharedDirectoryAccessError as error:
            self._post(self._shared_directory_unavailable, str(error))
        except Exception as error:
            self._post(self._finish_staging_error, str(error))
        else:
            self._post(
                self._finish_staging,
                selection,
                existing_selection,
            )

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

    def _finish_staging(
        self,
        selection: StagedSelection,
        existing_selection: StagedSelection | None,
    ) -> None:
        self._staging = False
        if self._closing:
            cleanup_staged_selection(selection)
            return
        if self._selected_selection is not existing_selection:
            cleanup_staged_selection(selection)
            self._finish_staging_error(
                "La selezione è cambiata durante la preparazione dei file."
            )
            return
        try:
            self._selected_selection = (
                selection
                if existing_selection is None
                else existing_selection.merged_with(selection)
            )
        except ValueError as error:
            cleanup_staged_selection(selection)
            self._finish_staging_error(str(error))
            return
        self._refresh_selection_view()
        if self.send_status is not None:
            self.send_status.text = "Contenuto pronto per la preparazione."
            self.send_status.label_color = SUCCESS_COLOR
        self._update_controls()

    def _remove_selected_document(self, index: int) -> None:
        selection = self._selected_selection
        if selection is None or not self._selection_can_be_changed():
            self._update_controls()
            return
        try:
            remaining, removed = selection.without_document(index)
        except IndexError:
            self._refresh_selection_view()
            self._update_controls()
            return
        self._selected_selection = remaining
        cleanup_staged_document(removed)
        self._refresh_selection_view()
        if self.send_status is not None:
            self.send_status.text = (
                "Elemento rimosso dalla selezione."
                if remaining is not None
                else "Selezione svuotata."
            )
            self.send_status.label_color = MUTED_COLOR
        self._update_controls()

    def _clear_selection(self, *_args: object) -> None:
        selection = self._selected_selection
        if selection is None or not self._selection_can_be_changed():
            self._update_controls()
            return
        self._selected_selection = None
        cleanup_staged_selection(selection)
        self._refresh_selection_view()
        if self.send_status is not None:
            self.send_status.text = "Selezione svuotata."
            self.send_status.label_color = MUTED_COLOR
        self._update_controls()

    def _refresh_selection_view(self) -> None:
        container = self.selection_list
        if container is None:
            return
        container.data = []
        selection = self._selected_selection
        if selection is None:
            if self.file_status is not None:
                self.file_status.text = "Nessun elemento selezionato."
                self.file_status.label_color = MUTED_COLOR
            return

        if self.file_status is not None:
            counts: list[str] = []
            if selection.file_root_count:
                counts.append(
                    "1 file"
                    if selection.file_root_count == 1
                    else f"{selection.file_root_count} file"
                )
            if selection.directory_root_count:
                counts.append(
                    "1 cartella"
                    if selection.directory_root_count == 1
                    else f"{selection.directory_root_count} cartelle"
                )
            self.file_status.text = (
                f"Selezione: {', '.join(counts)}\n"
                f"{format_file_size(selection.total_size)}"
            )
            self.file_status.label_color = TEXT_COLOR

        container.data = [
            {
                "item_index": index,
                "title": document.filename,
                "detail": (
                    "Cartella | " if document.is_directory else "File | "
                )
                + format_file_size(document.size),
                "icon_source": theme.icon_path(
                    "folder" if document.is_directory else "file"
                ),
                "remove_callback": self._remove_selected_document,
            }
            for index, document in enumerate(selection.documents)
        ]

    def _selection_can_be_changed(self) -> bool:
        return self._derive_controls().manage_selection

    def _finish_staging_cancelled(self) -> None:
        self._staging = False
        if self.send_status is not None:
            self.send_status.text = "Copia del contenuto interrotta."
        self._update_controls()

    def _finish_staging_error(self, message: str) -> None:
        self._staging = False
        if self.send_status is not None:
            self.send_status.text = "Impossibile preparare il contenuto selezionato."
            self.send_status.label_color = ERROR_COLOR
        self._show_error("Preparazione contenuto non riuscita", message)
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
                f"0 B / {format_file_size(selection.total_size)}"
            )
        self._set_send_metrics(
            speed=None,
            remaining=None,
            elapsed=None,
            transferred=0,
            total=selection.total_size,
        )
        if self.send_waiting_title is not None:
            self.send_waiting_title.text = "Preparazione invio"
        if self.send_payload_summary is not None:
            self.send_payload_summary.text = "Analisi del contenuto in corso..."

        try:
            client = TransferServiceClient.for_send(self._cache_root, selection)
            client.start()
        except Exception as error:
            self._show_error("Invio non avviato", str(error))
        else:
            self._selected_selection = None
            self._refresh_selection_view()
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
        if self.send_waiting_title is not None:
            self.send_waiting_title.text = {
                AndroidSendState.PREPARING: "Preparazione invio",
                AndroidSendState.SENDING_METADATA: "Invio informazioni",
                AndroidSendState.AWAITING_DECISION: "In attesa del destinatario",
            }.get(state, self.send_waiting_title.text)
        self._update_controls()

    def _on_send_status(self, message: str) -> None:
        if self.send_status is not None:
            self.send_status.text = message
            self.send_status.label_color = TEXT_COLOR

    def _on_send_prepared(
        self,
        proposal: TransferSummary,
        code: str,
    ) -> None:
        code_changed = self._code != code
        self._code = code
        payload_label = self._proposal_payload_label(proposal)
        if self.file_status is not None:
            self.file_status.text = (
                f"{payload_label}\n{format_file_size(proposal.size)}"
            )
            self.file_status.label_color = TEXT_COLOR
        if self.code_input is not None:
            self.code_input.text = self._format_display_code(code)
        if self.send_payload_summary is not None:
            self.send_payload_summary.text = (
                f"{payload_label}\n{format_file_size(proposal.size)}"
            )
        if self.send_transfer_summary is not None:
            self.send_transfer_summary.text = payload_label
        if self.progress_details is not None:
            self.progress_details.text = (
                f"0 B / {format_file_size(proposal.size)}"
            )
        self._set_send_metrics(
            speed=None,
            remaining=None,
            elapsed=None,
            transferred=0,
            total=proposal.size,
        )
        if code_changed:
            Clipboard.copy(code)
            self._show_snackbar("Codice copiato negli appunti")
        self._update_controls()

    def _on_send_progress(self, sample: TransferProgressSample) -> None:
        percent = sample.percent or 0
        transferred = sample.transferred_bytes or 0
        total = sample.total_bytes
        if self.progress_bar is not None:
            self.progress_bar.value = percent
        if self.send_percent is not None:
            self.send_percent.text = f"{percent:.0f}%"

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
                f"{format_file_size(transferred)} / {total_text}"
            )
        self._set_send_metrics(
            speed=sample.speed_bps,
            remaining=remaining,
            elapsed=elapsed,
            transferred=transferred,
            total=total,
        )

    def _on_send_finished(
        self,
        state: AndroidSendState,
        message: str,
    ) -> None:
        self._send_state = state
        self._selected_selection = None
        self._code = None
        self._refresh_selection_view()
        if self.code_input is not None:
            self.code_input.text = ""
        if self.send_status is not None:
            self.send_status.text = message
            self.send_status.label_color = (
                SUCCESS_COLOR
                if state == AndroidSendState.COMPLETED
                else MUTED_COLOR
                if state in {AndroidSendState.CANCELLED, AndroidSendState.REJECTED}
                else ERROR_COLOR
            )
        if state == AndroidSendState.COMPLETED and self.progress_bar is not None:
            self.progress_bar.value = 100
        self._configure_send_result(state, message)
        self._update_controls()

    def _set_send_metrics(
        self,
        *,
        speed: float | None,
        remaining: float | None,
        elapsed: float | None,
        transferred: int,
        total: int | None,
    ) -> None:
        if self.send_speed_metric is not None:
            self.send_speed_metric.value = format_transfer_rate(speed)
        if self.send_remaining_metric is not None:
            self.send_remaining_metric.value = format_duration(remaining)
        if self.send_elapsed_metric is not None:
            self.send_elapsed_metric.value = format_duration(elapsed)
        if self.send_transferred_metric is not None:
            total_text = format_file_size(total) if total is not None else "-"
            self.send_transferred_metric.value = (
                f"{format_file_size(transferred)} / {total_text}"
            )

    def _configure_send_result(
        self,
        state: AndroidSendState,
        message: str,
    ) -> None:
        panel = self.send_result_panel
        if panel is None:
            return
        title, icon = {
            AndroidSendState.COMPLETED: (
                "Invio completato",
                "circle-check",
            ),
            AndroidSendState.REJECTED: (
                "Trasferimento rifiutato",
                "circle-alert",
            ),
            AndroidSendState.CANCELLED: (
                "Invio interrotto",
                "x",
            ),
            AndroidSendState.FAILED: (
                "Invio non riuscito",
                "circle-alert",
            ),
        }.get(state, ("Invio terminato", "info"))
        panel.title = title
        panel.message = message
        panel.icon_source = theme.icon_path(icon)
        panel.tone = send_result_tone(state).value

    def _reset_send_view(self, *_args: object) -> None:
        if self._service_client is not None or self._service_is_releasing():
            return
        self._send_state = AndroidSendState.IDLE
        self._code = None
        self._transfer_started_at = None
        if self.code_input is not None:
            self.code_input.text = ""
        if self.progress_bar is not None:
            self.progress_bar.value = 0
        if self.send_percent is not None:
            self.send_percent.text = "0%"
        if self.send_status is not None:
            self.send_status.text = "Seleziona file o cartelle per iniziare."
            self.send_status.label_color = MUTED_COLOR
        self._refresh_selection_view()
        self._switch_mode("send")
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
            self.receive_proposal.label_color = MUTED_COLOR
        if self.receive_progress_bar is not None:
            self.receive_progress_bar.value = 0
        if self.receive_progress_details is not None:
            self.receive_progress_details.text = "0 B / -"
        if self.receive_save_progress_bar is not None:
            self.receive_save_progress_bar.value = 0
        if self.receive_save_progress_details is not None:
            self.receive_save_progress_details.text = "0 B / -"
        self._set_receive_metrics(
            speed=None,
            remaining=None,
            elapsed=None,
            transferred=0,
            total=None,
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
            self.receive_status.label_color = TEXT_COLOR

    def _on_receive_proposal(self, proposal: TransferSummary) -> None:
        self._receive_proposal = proposal
        payload_label = self._proposal_payload_label(proposal)
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
            self.receive_proposal.label_color = TEXT_COLOR
        if self.receive_transfer_summary is not None:
            self.receive_transfer_summary.text = payload_label
        if self.receive_save_summary is not None:
            self.receive_save_summary.text = (
                f"{payload_label}\n{format_file_size(proposal.size)}"
            )
        if self.receive_progress_details is not None:
            self.receive_progress_details.text = (
                f"0 B / {format_file_size(proposal.size)}"
            )
        self._set_receive_metrics(
            speed=None,
            remaining=None,
            elapsed=None,
            transferred=0,
            total=proposal.size,
        )
        self._update_controls()

    def _on_receive_progress(self, sample: TransferProgressSample) -> None:
        percent = sample.percent or 0
        transferred = sample.transferred_bytes or 0
        total = sample.total_bytes
        if self.receive_progress_bar is not None:
            self.receive_progress_bar.value = percent
        if self.receive_percent is not None:
            self.receive_percent.text = f"{percent:.0f}%"

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
                f"{format_file_size(transferred)} / {total_text}"
            )
        self._set_receive_metrics(
            speed=sample.speed_bps,
            remaining=remaining,
            elapsed=elapsed,
            transferred=transferred,
            total=total,
        )

    def _on_receive_save_ready(self, proposal: TransferSummary) -> None:
        self._receive_proposal = proposal
        if self.receive_progress_bar is not None:
            self.receive_progress_bar.value = 100
        if self.receive_percent is not None:
            self.receive_percent.text = "100%"
        if self.receive_save_summary is not None:
            self.receive_save_summary.text = (
                f"{self._proposal_payload_label(proposal)}\n"
                f"{format_file_size(proposal.size)}"
            )
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
            self.receive_status.label_color = MUTED_COLOR
        self._update_controls()

    def _save_destination_error(self, error: Exception) -> None:
        self._show_error("Destinazione non disponibile", str(error))
        self._update_controls()

    def _on_receive_save_progress(self, copied: int, total: int) -> None:
        percent = (copied * 100 / total) if total else 100
        if self.receive_save_progress_bar is not None:
            self.receive_save_progress_bar.value = percent
        if self.receive_save_progress_details is not None:
            self.receive_save_progress_details.text = (
                f"{format_file_size(copied)} / {format_file_size(total)}"
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
            self.receive_status.label_color = (
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
        if (
            state == AndroidReceiveState.COMPLETED
            and self.receive_save_progress_bar is not None
        ):
            self.receive_save_progress_bar.value = 100
        self._configure_receive_result(state, message)
        self._update_controls()

    def _set_receive_metrics(
        self,
        *,
        speed: float | None,
        remaining: float | None,
        elapsed: float | None,
        transferred: int,
        total: int | None,
    ) -> None:
        if self.receive_speed_metric is not None:
            self.receive_speed_metric.value = format_transfer_rate(speed)
        if self.receive_remaining_metric is not None:
            self.receive_remaining_metric.value = format_duration(remaining)
        if self.receive_elapsed_metric is not None:
            self.receive_elapsed_metric.value = format_duration(elapsed)
        if self.receive_transferred_metric is not None:
            total_text = format_file_size(total) if total is not None else "-"
            self.receive_transferred_metric.value = (
                f"{format_file_size(transferred)} / {total_text}"
            )

    def _configure_receive_result(
        self,
        state: AndroidReceiveState,
        message: str,
    ) -> None:
        panel = self.receive_result_panel
        if panel is None:
            return
        title, icon = {
            AndroidReceiveState.COMPLETED: (
                "Ricezione completata",
                "circle-check",
            ),
            AndroidReceiveState.REJECTED: (
                "Trasferimento rifiutato",
                "circle-alert",
            ),
            AndroidReceiveState.CANCELLED: (
                "Ricezione interrotta",
                "x",
            ),
            AndroidReceiveState.FAILED: (
                "Ricezione non riuscita",
                "circle-alert",
            ),
        }.get(state, ("Ricezione terminata", "info"))
        panel.title = title
        panel.message = message
        panel.icon_source = theme.icon_path(icon)
        panel.tone = receive_result_tone(state).value

    def _reset_receive_view(self, *_args: object) -> None:
        if self._service_client is not None or self._service_is_releasing():
            return
        self._receive_state = AndroidReceiveState.IDLE
        self._receive_proposal = None
        self._receive_started_at = None
        if self.receive_code_input is not None:
            self.receive_code_input.text = ""
        if self.receive_progress_bar is not None:
            self.receive_progress_bar.value = 0
        if self.receive_save_progress_bar is not None:
            self.receive_save_progress_bar.value = 0
        if self.receive_percent is not None:
            self.receive_percent.text = "0%"
        if self.receive_status is not None:
            self.receive_status.text = (
                "Inserisci il codice comunicato dal mittente."
            )
            self.receive_status.label_color = MUTED_COLOR
        self._switch_mode("receive")
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

    def _poll_shared_intents(self, *_args: object) -> None:
        if self._closing or self._share_activity is None or self._dialog_overlay is not None:
            return
        try:
            intent = self._share_activity.consumeSharedIntent()
            if intent is not None:
                self._handle_shared_intent(intent)
        except Exception as error:
            self._show_error("Condivisione non riuscita", str(error))

    def _handle_shared_intent(self, intent: Any) -> None:
        content = read_shared_intent(intent)
        if content is None:
            return
        if not self._derive_controls().select_file:
            self._show_error(
                "MoonTransfer occupato",
                "Completa o interrompi l'operazione corrente, poi condividi nuovamente il contenuto.",
            )
            return
        if content.uris:
            self._reset_send_view()
            self._stage_selected_uri(content.uris, is_directory=False, shared=True)
            return
        if len(content.codes) != 1:
            previous_code = self.receive_code_input.text if self.receive_code_input is not None else ""
            self._reset_receive_view()
            if self.receive_code_input is not None:
                self.receive_code_input.text = previous_code
            self._show_error(
                "Più codici ricevuti",
                "Condividi un solo codice oppure inserisci quello desiderato in Ricevi.\n\n"
                + "\n".join(content.codes),
            )
            return
        code = content.codes[0]
        if self.receive_code_input is not None and self.receive_code_input.text.strip():
            if "".join(self.receive_code_input.text.split()) != code:
                self._open_dialog(
                    title="Sostituire il codice?",
                    message="In Ricevi è già presente un codice. Vuoi usare quello condiviso?",
                    secondary_text="Usa codice condiviso",
                    secondary_callback=lambda: self._use_shared_code(code),
                )
                return
        self._use_shared_code(code)

    def _use_shared_code(self, code: str) -> None:
        if self._dialog_overlay is not None:
            self._close_dialog(self._dialog_overlay)
        if not self._derive_controls().select_file:
            self._show_error("MoonTransfer occupato", "Riprova dopo l'operazione corrente.")
            return
        self._reset_receive_view()
        if self.receive_code_input is not None:
            self.receive_code_input.text = code
        self._show_snackbar("Codice ricevuto")
        self._update_controls()

    def _shared_directory_unavailable(self, message: str) -> None:
        self._staging = False
        if self._closing:
            return
        self._update_controls()
        self._open_dialog(
            title="Seleziona la cartella",
            message=message,
            secondary_text="Seleziona cartella",
            secondary_callback=self._pick_shared_directory,
        )

    def _pick_shared_directory(self) -> None:
        if self._dialog_overlay is not None:
            self._close_dialog(self._dialog_overlay)
        if self._derive_controls().select_file:
            self._open_directory_picker()

    def _share_code(self, *_args: object) -> None:
        if not self._code or platform != "android":
            return
        try:
            share_code(self._code)
        except Exception:
            self._show_error("Condivisione non disponibile", "Impossibile condividere il codice con altre app.")

    def _copy_code(self, *_args: object) -> None:
        if not self._code:
            return
        Clipboard.copy(self._code)
        if self.send_status is not None:
            self.send_status.text = "Codice copiato negli appunti."
        self._show_snackbar("Codice copiato negli appunti")

    def _on_receive_code_changed(self, widget: MoonTextInput, value: str) -> None:
        try:
            codes = codes_from_shared_text(value)
        except AndroidShareError:
            codes = ()
        if len(codes) == 1 and value != codes[0]:
            widget.text = codes[0]
        self._update_controls()

    def _paste_receive_code(self, *_args: object) -> None:
        if self.receive_code_input is None or self.receive_code_input.disabled:
            return
        value = Clipboard.paste()
        if value is None:
            return
        try:
            codes = codes_from_shared_text(str(value))
        except AndroidShareError as error:
            self._show_error("Codice non valido", str(error))
            return
        if len(codes) != 1:
            self._show_error(
                "Più codici ricevuti",
                "Copia un solo codice oppure inserisci quello desiderato in Ricevi.",
            )
            return
        self.receive_code_input.text = codes[0]
        self._show_snackbar("Codice incollato")

    @staticmethod
    def _format_display_code(code: str) -> str:
        return " ".join(code[index : index + 8] for index in range(0, len(code), 8))

    @staticmethod
    def _proposal_payload_label(proposal: TransferSummary) -> str:
        if proposal.is_single_file:
            return proposal.filename
        counts = [f"{proposal.file_count} file"]
        if proposal.directory_count:
            counts.append(
                "1 cartella"
                if proposal.directory_count == 1
                else f"{proposal.directory_count} cartelle"
            )
        return " | ".join(counts)

    def _show_build_info(self, *_args: object) -> None:
        diagnostics = CURRENT_BUILD.diagnostics()
        self._open_dialog(
            title="Informazioni su MoonTransfer",
            message=(
                "Versione, protocollo e componenti inclusi in questa build."
            ),
            details=diagnostics,
            secondary_text="Copia diagnostica",
            secondary_callback=lambda: self._copy_diagnostics(diagnostics),
        )

    def _copy_diagnostics(self, diagnostics: str) -> None:
        Clipboard.copy(diagnostics)
        self._show_snackbar("Diagnostica copiata")

    def _derive_controls(self) -> AndroidControlState:
        picker_pending = bool(self._picker and self._picker.pending)
        save_picker_pending = bool(
            self._save_picker and self._save_picker.pending
        )
        service_operation = (
            self._service_client.operation
            if self._service_client is not None
            else None
        )
        return derive_android_control_state(
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

    def _update_controls(self) -> None:
        self._update_stage_views()
        controls = self._derive_controls()
        if self.select_button is not None:
            self.select_button.disabled = not controls.select_file
        if self.select_directory_button is not None:
            self.select_directory_button.disabled = not controls.select_file
        if self.clear_selection_button is not None:
            self.clear_selection_button.disabled = not controls.manage_selection
        if self.selection_list is not None:
            self.selection_list.disabled = not controls.manage_selection
        if self.send_button is not None:
            self.send_button.disabled = not controls.start_send
        if self.cancel_button is not None:
            self.cancel_button.disabled = not controls.cancel_send
        if self.transfer_cancel_button is not None:
            self.transfer_cancel_button.disabled = not controls.cancel_send
        if self.copy_button is not None:
            self.copy_button.disabled = not controls.copy_code
        if self.share_button is not None:
            self.share_button.disabled = platform != "android" or not controls.copy_code
        if self.receive_code_input is not None:
            self.receive_code_input.disabled = not controls.edit_receive_code
        if self.receive_paste_button is not None:
            self.receive_paste_button.disabled = not controls.edit_receive_code
        if self.receive_start_button is not None:
            self.receive_start_button.disabled = not controls.start_receive
        if self.receive_loading_cancel_button is not None:
            self.receive_loading_cancel_button.disabled = (
                not controls.cancel_receive
            )
        if self.receive_accept_button is not None:
            self.receive_accept_button.disabled = not controls.accept_receive
        if self.receive_reject_button is not None:
            self.receive_reject_button.disabled = not controls.reject_receive
        if self.receive_save_button is not None:
            self.receive_save_button.disabled = not controls.save_receive
        if self.receive_cancel_button is not None:
            self.receive_cancel_button.disabled = not controls.cancel_receive
        if self.receive_save_cancel_button is not None:
            self.receive_save_cancel_button.disabled = (
                not controls.cancel_receive
            )
        if self.probe_button is not None:
            self.probe_button.disabled = not controls.probe_transport
        service_operation = (
            self._service_client.operation
            if self._service_client is not None
            else None
        )
        if self.send_mode_button is not None:
            self.send_mode_button.disabled = (
                service_operation is TransferServiceOperation.RECEIVE
            )
        if self.receive_mode_button is not None:
            self.receive_mode_button.disabled = (
                service_operation is TransferServiceOperation.SEND
            )
        reset_disabled = (
            self._service_client is not None or self._service_is_releasing()
        )
        if self.send_reset_button is not None:
            self.send_reset_button.disabled = reset_disabled
        if self.receive_reset_button is not None:
            self.receive_reset_button.disabled = reset_disabled

    def _receive_code_is_valid(self) -> bool:
        if self.receive_code_input is None:
            return False
        try:
            validate_croc_code(self.receive_code_input.text.strip())
        except Exception:
            return False
        return True

    def _show_error(self, title: str, message: str) -> None:
        self._open_dialog(
            title=title,
            message=message,
        )

    def _open_dialog(
        self,
        *,
        title: str,
        message: str,
        details: str = "",
        secondary_text: str = "",
        secondary_callback: Any = None,
    ) -> None:
        root = self.root
        if not isinstance(root, MoonTransferRoot):
            print(f"[dialog] {title}: {message}", flush=True)
            return
        if self._dialog_overlay is not None:
            self._close_dialog(self._dialog_overlay)
        overlay = MoonDialogOverlay(
            title=title,
            message=message,
            details=details,
            secondary_text=secondary_text,
        )
        overlay.primary_callback = lambda: self._close_dialog(overlay)
        overlay.secondary_callback = secondary_callback
        self._dialog_overlay = overlay
        root.add_widget(overlay)

    def _close_dialog(self, overlay: MoonDialogOverlay) -> None:
        root = self.root
        if isinstance(root, MoonTransferRoot) and overlay.parent is root:
            root.remove_widget(overlay)
        if self._dialog_overlay is overlay:
            self._dialog_overlay = None

    def _show_snackbar(self, message: str) -> None:
        snackbar = self.snackbar
        if snackbar is None:
            return
        if self._snackbar_event is not None:
            self._snackbar_event.cancel()
        Animation.cancel_all(snackbar, "opacity")
        snackbar.text = message
        snackbar.disabled = False
        Animation(opacity=1, duration=0.12).start(snackbar)
        self._snackbar_event = Clock.schedule_once(
            self._hide_snackbar,
            2.4,
        )

    def _hide_snackbar(self, *_args: object) -> None:
        self._snackbar_event = None
        snackbar = self.snackbar
        if snackbar is None:
            return
        animation = Animation(opacity=0, duration=0.16)
        animation.bind(
            on_complete=lambda *_animation_args: setattr(
                snackbar,
                "disabled",
                True,
            )
        )
        animation.start(snackbar)

    @staticmethod
    def _post(callback: Any, *args: object) -> None:
        Clock.schedule_once(lambda _dt: callback(*args))


def main() -> None:
    MoonTransferAndroidApp().run()

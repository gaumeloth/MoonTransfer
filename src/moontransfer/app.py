from __future__ import annotations

import stat
import sys
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from moontransfer import croc
from moontransfer.desktop import open_folder
from moontransfer.files import (
    DestinationCheck,
    DestinationConflict,
    is_link_or_reparse,
    unique_directory_path,
    unique_destination_path,
)
from moontransfer.progress import format_file_size
from moontransfer.protocol import (
    ProtocolError,
    TransferProposal,
    validate_croc_code,
)
from moontransfer.resources import APP_ICON_PATH
from moontransfer.runner import CrocRunner
from moontransfer.transfer import (
    BaseTransferController,
    ReceiveDecision,
    ReceiveTransferController,
    SendTransferController,
)
from moontransfer.widgets import (
    StatusLabel,
    TechnicalOutput,
    TransferProgressWidget,
    add_expandable_output,
    plain_message_box,
)


def configure_application(app: QApplication) -> None:
    app.setApplicationName("MoonTransfer")
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))


def _connect_progress(
    controller: BaseTransferController,
    progress: TransferProgressWidget,
) -> None:
    controller.progress_preview_changed.connect(progress.set_total_preview)
    controller.progress_started.connect(
        lambda total, exact: progress.start(
            total_bytes=total,
            exact_total=exact,
        )
    )
    controller.progress_total_changed.connect(progress.set_total)
    controller.progress_sampled.connect(progress.apply_sample)
    controller.progress_finished.connect(
        lambda success: progress.finish(success=success)
    )


def _show_controller_error(
    parent: QWidget,
    title: str,
    text: str,
) -> None:
    plain_message_box(
        parent,
        icon=QMessageBox.Icon.Critical,
        title=title,
        text=text,
        standard_buttons=QMessageBox.StandardButton.Ok,
    ).exec()


class SendTab(QWidget):
    def __init__(self, croc_path: str) -> None:
        super().__init__()
        self.last_code: str | None = None
        self.source_paths: list[Path] = []

        self.status_label = StatusLabel(
            "Pronto a inviare file e cartelle."
        )
        self.source_list = QListWidget()
        self.source_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.source_list.setMinimumHeight(100)
        self.source_list.setMaximumHeight(150)
        self.source_list.setAlternatingRowColors(True)

        self.add_files_button = QPushButton("Aggiungi file")
        self.add_folder_button = QPushButton("Aggiungi cartella")
        self.remove_button = QPushButton("Rimuovi")
        self.remove_button.setEnabled(False)
        self.clear_selection_button = QPushButton("Svuota")
        self.clear_selection_button.setEnabled(False)

        self.add_files_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        )
        self.add_folder_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self.remove_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
        )
        self.clear_selection_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)
        )

        self.file_info_label = QLabel("Nessun elemento selezionato.")
        self.file_info_label.setTextFormat(Qt.TextFormat.PlainText)
        self.file_info_label.setWordWrap(True)
        self.file_info_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.start_button = QPushButton("Invia")
        self.start_button.setEnabled(False)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.code_edit = QLineEdit()
        self.code_edit.setReadOnly(True)
        self.code_edit.setPlaceholderText("Il codice apparirà qui")
        self.copy_button = QPushButton("Copia codice")
        self.copy_button.setEnabled(False)

        self.progress = TransferProgressWidget("Inviato")
        self.output = TechnicalOutput()
        self.terminal = self.output.terminal
        self.runners = {
            "metadata_send": self._make_runner(croc_path),
            "main_send": self._make_runner(croc_path),
        }
        self.controller = SendTransferController(
            croc_path=croc_path,
            runners=self.runners,
            parent=self,
        )
        self.controller.status_changed.connect(self.status_label.setText)
        self.controller.active_changed.connect(self._set_running)
        self.controller.code_changed.connect(self._set_code)
        self.controller.terminal_line.connect(self.terminal.append_line)
        self.controller.error_raised.connect(
            lambda title, text: _show_controller_error(self, title, text)
        )
        _connect_progress(self.controller, self.progress)

        selection_actions = QHBoxLayout()
        selection_actions.addWidget(self.add_files_button)
        selection_actions.addWidget(self.add_folder_button)
        selection_actions.addStretch(1)
        selection_actions.addWidget(self.remove_button)
        selection_actions.addWidget(self.clear_selection_button)

        control_row = QHBoxLayout()
        control_row.addWidget(self.start_button)
        control_row.addWidget(self.stop_button)
        control_row.addStretch(1)
        control_row.addWidget(QLabel("Codice:"))
        control_row.addWidget(self.code_edit, 1)
        control_row.addWidget(self.copy_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.source_list)
        layout.addLayout(selection_actions)
        layout.addWidget(self.file_info_label)
        layout.addLayout(control_row)
        layout.addWidget(self.progress)
        add_expandable_output(layout, self.output)

        self.add_files_button.clicked.connect(self._browse_files)
        self.add_folder_button.clicked.connect(self._browse_folder)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_selection_button.clicked.connect(self._clear_selection)
        self.source_list.itemSelectionChanged.connect(
            self._refresh_selection_actions
        )
        self.start_button.clicked.connect(self._start_send)
        self.stop_button.clicked.connect(self._stop_send)
        self.copy_button.clicked.connect(self._copy_code)
        self._refresh_selection_info()

    def stop_active_transfers(self) -> None:
        self.controller.stop()

    def _make_runner(self, croc_path: str) -> CrocRunner:
        return CrocRunner(
            croc_path,
            append_text=self.terminal.append_text,
            append_line=self.terminal.append_line,
        )

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleziona file da inviare",
            str(self._browse_start_directory()),
        )
        if paths:
            self._add_paths(Path(path) for path in paths)

    def _browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Seleziona cartella da inviare",
            str(self._browse_start_directory()),
        )
        if path:
            self._add_paths((Path(path),))

    def _browse_start_directory(self) -> Path:
        if self.source_paths:
            first = self.source_paths[0]
            return first if first.is_dir() else first.parent
        return Path.home()

    def _add_paths(self, paths: Iterable[Path]) -> None:
        known = {str(path) for path in self.source_paths}
        for selected in paths:
            path = selected.expanduser().absolute()
            if str(path) in known:
                continue
            known.add(str(path))
            self.source_paths.append(path)

            item = QListWidgetItem(self._source_description(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            if path.is_dir():
                item.setIcon(
                    self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
                )
            else:
                item.setIcon(
                    self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
                )
            self.source_list.addItem(item)
        self._refresh_selection_info()

    @staticmethod
    def _source_description(path: Path) -> str:
        kind = "Cartella" if path.is_dir() else "File"
        return f"{kind}: {path.name} ({path.parent})"

    def _remove_selected(self) -> None:
        selected_rows = sorted(
            {self.source_list.row(item) for item in self.source_list.selectedItems()},
            reverse=True,
        )
        for row in selected_rows:
            self.source_list.takeItem(row)
            del self.source_paths[row]
        self._refresh_selection_info()

    def _clear_selection(self) -> None:
        self.source_paths.clear()
        self.source_list.clear()
        self._refresh_selection_info()

    def _has_valid_selection(self) -> bool:
        if not self.source_paths:
            return False
        try:
            for path in self.source_paths:
                item_stat = path.lstat()
                if is_link_or_reparse(item_stat):
                    return False
                if not (
                    stat.S_ISREG(item_stat.st_mode)
                    or stat.S_ISDIR(item_stat.st_mode)
                ):
                    return False
        except OSError:
            return False
        return True

    def _refresh_selection_actions(self) -> None:
        running = self.controller.active
        self.remove_button.setEnabled(
            not running and bool(self.source_list.selectedItems())
        )
        self.clear_selection_button.setEnabled(
            not running and bool(self.source_paths)
        )

    def _refresh_selection_info(self) -> None:
        if not self.source_paths:
            self.file_info_label.setText("Nessun elemento selezionato.")
            self.start_button.setEnabled(False)
            self.progress.set_total_preview(None)
            self._refresh_selection_actions()
            return

        if not self._has_valid_selection():
            self.file_info_label.setText(
                "La selezione contiene un percorso non disponibile o non supportato."
            )
            self.start_button.setEnabled(False)
            self.progress.set_total_preview(None)
            self._refresh_selection_actions()
            return

        file_count = 0
        directory_count = 0
        selected_file_size = 0
        for path in self.source_paths:
            if path.is_dir():
                directory_count += 1
            else:
                file_count += 1
                selected_file_size += path.stat().st_size

        parts = []
        if file_count:
            parts.append(f"{file_count} file")
        if directory_count:
            parts.append(
                f"{directory_count} "
                + ("cartella" if directory_count == 1 else "cartelle")
            )
        summary = ", ".join(parts)
        if directory_count:
            detail = "La dimensione totale sarà calcolata prima dell'invio."
            preview_size = None
        else:
            detail = f"Dimensione totale: {format_file_size(selected_file_size)}."
            preview_size = selected_file_size

        self.file_info_label.setText(
            f"Elementi principali selezionati: {summary}. {detail}"
        )
        self.progress.set_total_preview(preview_size)
        if not self.controller.active:
            self.start_button.setEnabled(True)
            self.status_label.setText(
                "Selezione pronta. Premi Invia per generare il codice."
            )
        self._refresh_selection_actions()

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(
            False if running else self._has_valid_selection()
        )
        self.stop_button.setEnabled(running)
        self.add_files_button.setEnabled(not running)
        self.add_folder_button.setEnabled(not running)
        self.source_list.setEnabled(not running)
        self.copy_button.setEnabled(bool(self.last_code))
        self._refresh_selection_actions()

    def _set_code(self, code: str | None) -> None:
        self.last_code = code
        self.code_edit.setText(code or "")
        self.copy_button.setEnabled(bool(code))

    def _stop_send(self) -> None:
        self.controller.stop()

    def _start_send(self) -> None:
        if not self._has_valid_selection():
            self.status_label.setText(
                "Seleziona almeno un file o una cartella valida prima di inviare."
            )
            QMessageBox.warning(
                self,
                "Selezione non valida",
                "Seleziona almeno un file o una cartella valida.",
            )
            return

        try:
            self.controller.start(tuple(self.source_paths))
        except Exception as exc:
            self.status_label.setText("Impossibile avviare il trasferimento.")
            _show_controller_error(
                self,
                "Errore trasferimento",
                f"Impossibile avviare il trasferimento.\n\n{exc}",
            )

    def _copy_code(self) -> None:
        if self.last_code:
            QApplication.clipboard().setText(self.last_code)
            self.status_label.setText("Codice copiato negli appunti.")
            self.terminal.append_line()
            self.terminal.append_line("[clipboard] codice copiato")


class ReceiveTab(QWidget):
    def __init__(self, croc_path: str) -> None:
        super().__init__()

        self.status_label = StatusLabel("Pronto a ricevere un file.")
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("Incolla il codice ricevuto")
        self.dest_edit = QLineEdit(str(Path.home() / "Downloads"))
        self.dest_button = QPushButton("Scegli...")
        self.open_dest_button = QPushButton("Apri cartella")
        self.start_button = QPushButton("Ricevi")
        self.start_button.setEnabled(False)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)

        self.progress = TransferProgressWidget("Scaricato")
        self.output = TechnicalOutput()
        self.terminal = self.output.terminal
        self.runners = {
            "metadata_receive": self._make_runner(croc_path),
            "main_receive": self._make_runner(croc_path),
        }
        self.controller = ReceiveTransferController(
            croc_path=croc_path,
            runners=self.runners,
            acceptance_provider=lambda proposal: self._confirm_transfer(
                proposal
            ),
            conflict_resolver=lambda proposal, check: (
                self._resolve_destination_conflict(proposal, check)
            ),
            parent=self,
        )
        self.controller.status_changed.connect(self.status_label.setText)
        self.controller.active_changed.connect(self._set_running)
        self.controller.terminal_line.connect(self.terminal.append_line)
        self.controller.error_raised.connect(
            lambda title, text: _show_controller_error(self, title, text)
        )
        _connect_progress(self.controller, self.progress)

        code_row = QHBoxLayout()
        code_row.addWidget(QLabel("Codice:"))
        code_row.addWidget(self.code_edit, 1)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Destinazione:"))
        dest_row.addWidget(self.dest_edit, 1)
        dest_row.addWidget(self.dest_button)
        dest_row.addWidget(self.open_dest_button)

        control_row = QHBoxLayout()
        control_row.addWidget(self.start_button)
        control_row.addWidget(self.stop_button)
        control_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addLayout(code_row)
        layout.addLayout(dest_row)
        layout.addLayout(control_row)
        layout.addWidget(self.progress)
        add_expandable_output(layout, self.output)

        self.code_edit.textChanged.connect(self._refresh_receive_actions)
        self.dest_edit.textChanged.connect(self._refresh_receive_actions)
        self.dest_button.clicked.connect(self._choose_destination)
        self.open_dest_button.clicked.connect(self._open_destination)
        self.start_button.clicked.connect(self._start_receive)
        self.stop_button.clicked.connect(self._stop_receive)
        self._refresh_receive_actions()

    def stop_active_transfers(self) -> None:
        self.controller.stop()

    def _make_runner(self, croc_path: str) -> CrocRunner:
        return CrocRunner(
            croc_path,
            append_text=self.terminal.append_text,
            append_line=self.terminal.append_line,
        )

    def _choose_destination(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Scegli cartella di destinazione",
            self.dest_edit.text().strip() or str(Path.home()),
        )
        if path:
            self.dest_edit.setText(path)
            self.status_label.setText(
                "Cartella di destinazione selezionata."
            )
            self._refresh_receive_actions()

    def _destination(self) -> Path:
        return Path(self.dest_edit.text().strip())

    def _can_open_destination(self) -> bool:
        destination_text = self.dest_edit.text().strip()
        return bool(destination_text and Path(destination_text).is_dir())

    def _can_start_receive(self) -> bool:
        return bool(
            self.code_edit.text().strip() and self.dest_edit.text().strip()
        )

    def _refresh_receive_actions(self) -> None:
        running = self.controller.active or self.controller.any_running()
        self.start_button.setEnabled(
            not running and self._can_start_receive()
        )
        self.open_dest_button.setEnabled(
            self._can_open_destination() and not running
        )

    def _open_destination(self) -> None:
        destination = self._destination()
        if not destination.is_dir():
            self.status_label.setText(
                "La cartella di destinazione non esiste ancora."
            )
            QMessageBox.warning(
                self,
                "Cartella non disponibile",
                "La cartella di destinazione non esiste ancora.",
            )
            self._refresh_receive_actions()
            return

        result = open_folder(destination)
        if result.opened:
            self.status_label.setText(
                "Cartella di destinazione aperta."
            )
        else:
            self.status_label.setText(
                "Impossibile aprire la cartella di destinazione."
            )
            details = (
                f"\n\nDettaglio tecnico:\n{result.error}"
                if result.error
                else ""
            )
            plain_message_box(
                self,
                icon=QMessageBox.Icon.Warning,
                title="Apertura non riuscita",
                text=(
                    "Non riesco ad aprire la cartella con il file manager "
                    "del sistema."
                    + details
                ),
                standard_buttons=QMessageBox.StandardButton.Ok,
            ).exec()

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(
            False if running else self._can_start_receive()
        )
        self.stop_button.setEnabled(running)
        self.code_edit.setEnabled(not running)
        self.dest_edit.setEnabled(not running)
        self.dest_button.setEnabled(not running)
        self.open_dest_button.setEnabled(
            not running and self._can_open_destination()
        )

    def _stop_receive(self) -> None:
        self.controller.stop()

    def _start_receive(self) -> None:
        code = self.code_edit.text().strip()
        destination_text = self.dest_edit.text().strip()

        if not code:
            self.status_label.setText(
                "Inserisci il codice ricevuto prima di avviare la ricezione."
            )
            QMessageBox.warning(
                self,
                "Codice mancante",
                "Incolla il codice ricevuto.",
            )
            return

        try:
            code = validate_croc_code(code)
        except ProtocolError as exc:
            self.status_label.setText("Il codice inserito non è valido.")
            plain_message_box(
                self,
                icon=QMessageBox.Icon.Warning,
                title="Codice non valido",
                text=str(exc),
                standard_buttons=QMessageBox.StandardButton.Ok,
            ).exec()
            return

        if not destination_text:
            self.status_label.setText(
                "Scegli una cartella di destinazione."
            )
            QMessageBox.warning(
                self,
                "Destinazione mancante",
                "Scegli una cartella di destinazione.",
            )
            return

        try:
            self.controller.start(code, Path(destination_text))
        except Exception as exc:
            self.status_label.setText(
                "Impossibile avviare la ricezione."
            )
            _show_controller_error(
                self,
                "Errore trasferimento",
                f"Impossibile avviare la ricezione.\n\n{exc}",
            )

    def _confirm_transfer(
        self,
        proposal: TransferProposal,
    ) -> bool:
        object_name = "questo file" if proposal.is_single_file else "questo contenuto"
        answer_box = plain_message_box(
            self,
            icon=QMessageBox.Icon.Question,
            title="Accetta trasferimento",
            text=(
                f"{self._proposal_details(proposal)}\n\n"
                f"Vuoi ricevere {object_name}?"
            ),
            standard_buttons=(
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
            default_button=QMessageBox.StandardButton.No,
        )
        if not proposal.is_single_file:
            answer_box.setDetailedText(
                self._proposal_manifest_details(proposal)
            )
        return answer_box.exec() == QMessageBox.StandardButton.Yes

    def _resolve_destination_conflict(
        self,
        proposal: TransferProposal,
        check: DestinationCheck,
    ) -> ReceiveDecision:
        if check.conflict == DestinationConflict.NONE:
            return ReceiveDecision.accept(check.path, overwrite=False)

        details = self._proposal_details(proposal)
        if not proposal.is_single_file:
            suggested = unique_directory_path(check.path)
            identical = check.conflict == DestinationConflict.IDENTICAL
            box = plain_message_box(
                self,
                icon=(
                    QMessageBox.Icon.Information
                    if identical
                    else QMessageBox.Icon.Warning
                ),
                title=(
                    "Contenuto già presente"
                    if identical
                    else "Nome già esistente"
                ),
                text=(
                    f"{details}\n\n"
                    + (
                        "Nella destinazione esiste già lo stesso contenuto."
                        if identical
                        else (
                            "Nella destinazione esiste già un elemento con lo "
                            "stesso nome, ma il contenuto è diverso."
                        )
                    )
                    + "\n\nLe cartelle esistenti non vengono unite o sovrascritte."
                ),
            )
            save_button = box.addButton(
                f"Salva come {suggested.name}",
                QMessageBox.ButtonRole.AcceptRole,
            )
            reject_button = box.addButton(
                "Non scaricare" if identical else "Rifiuta",
                QMessageBox.ButtonRole.RejectRole,
            )
            box.setDefaultButton(reject_button)
            box.exec()
            if box.clickedButton() is save_button:
                return ReceiveDecision.accept(suggested, overwrite=False)
            return ReceiveDecision.reject()

        if check.conflict == DestinationConflict.IDENTICAL:
            box = plain_message_box(
                self,
                icon=QMessageBox.Icon.Information,
                title="File già presente",
                text=(
                    f"{details}\n\n"
                    "Nella destinazione esiste già lo stesso file."
                ),
            )
            skip_button = box.addButton(
                "Non scaricare",
                QMessageBox.ButtonRole.RejectRole,
            )
            receive_button = box.addButton(
                "Scarica comunque",
                QMessageBox.ButtonRole.AcceptRole,
            )
            box.setDefaultButton(skip_button)
            box.exec()

            if box.clickedButton() is receive_button:
                return ReceiveDecision.accept(check.path, overwrite=True)
            return ReceiveDecision.reject()

        box = plain_message_box(
            self,
            icon=QMessageBox.Icon.Warning,
            title="File già esistente",
            text=(
                f"{details}\n\n"
                "Nella destinazione esiste già un file con lo stesso nome, "
                "ma il contenuto è diverso."
            ),
        )
        overwrite_button = box.addButton(
            "Sovrascrivi",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        rename_button = box.addButton(
            "Salva con altro nome",
            QMessageBox.ButtonRole.AcceptRole,
        )
        box.addButton(
            "Rifiuta",
            QMessageBox.ButtonRole.RejectRole,
        )
        box.setDefaultButton(rename_button)
        box.exec()

        clicked = box.clickedButton()
        if clicked is overwrite_button:
            return ReceiveDecision.accept(check.path, overwrite=True)

        if clicked is rename_button:
            suggested = unique_destination_path(check.path)
            selected, _ = QFileDialog.getSaveFileName(
                self,
                "Salva file come",
                str(suggested),
            )
            if selected:
                target = Path(selected)
                return ReceiveDecision.accept(
                    target,
                    overwrite=target.exists(),
                )

        return ReceiveDecision.reject()

    @staticmethod
    def _proposal_details(proposal: TransferProposal) -> str:
        if proposal.is_single_file:
            return (
                f"Nome: {proposal.filename}\n"
                f"Dimensione: {format_file_size(proposal.size)}\n"
                f"SHA-256: {proposal.sha256}"
            )

        roots = ", ".join(proposal.roots[:8])
        if len(proposal.roots) > 8:
            roots += f", e altri {len(proposal.roots) - 8}"
        kind = "Cartella" if len(proposal.roots) == 1 else "Gruppo"
        return (
            f"Tipo: {kind}\n"
            f"Elementi principali: {roots}\n"
            f"Contenuto: {proposal.file_count} file, "
            f"{proposal.directory_count} cartelle\n"
            f"Dimensione totale: {format_file_size(proposal.size)}\n"
            "Integrità: SHA-256 verificato per ogni file"
        )

    @staticmethod
    def _proposal_manifest_details(proposal: TransferProposal) -> str:
        lines = ["Manifest del trasferimento:"]
        for entry in proposal.entries:
            if entry.is_directory:
                lines.append(f"Cartella  {entry.path}")
            else:
                lines.append(
                    f"File      {entry.path}  "
                    f"{format_file_size(entry.size or 0)}  {entry.sha256}"
                )
        return "\n".join(lines)


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MoonTransfer")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self._close_pending = False

        croc_path = croc.find_executable()
        if not croc_path:
            QMessageBox.critical(
                self,
                "croc non trovato",
                "Esegui prima: uv run python tools/fetch_croc.py",
            )
            raise SystemExit(1)

        tabs = QTabWidget()
        self.send_tab = SendTab(croc_path)
        self.receive_tab = ReceiveTab(croc_path)
        self.send_tab.controller.shutdown_finished.connect(
            self._schedule_pending_close
        )
        self.receive_tab.controller.shutdown_finished.connect(
            self._schedule_pending_close
        )
        tabs.addTab(self.send_tab, "Invia")
        tabs.addTab(self.receive_tab, "Ricevi")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        self.resize(900, self.sizeHint().height())

    def _controllers_busy(self) -> bool:
        return (
            self.send_tab.controller.busy
            or self.receive_tab.controller.busy
        )

    def _schedule_pending_close(self) -> None:
        if self._close_pending:
            QTimer.singleShot(0, self._complete_pending_close)

    def _complete_pending_close(self) -> None:
        if self._close_pending and not self._controllers_busy():
            self._close_pending = False
            self.close()

    def closeEvent(self, event) -> None:  # noqa: ANN001
        if not self._controllers_busy():
            self._close_pending = False
            event.accept()
            return

        event.ignore()
        if self._close_pending:
            return

        self._close_pending = True
        self.send_tab.stop_active_transfers()
        self.receive_tab.stop_active_transfers()
        self._schedule_pending_close()


def main() -> None:
    app = QApplication(sys.argv)
    configure_application(app)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()

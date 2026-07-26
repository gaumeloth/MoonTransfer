from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from moontransfer import croc
from moontransfer.desktop import open_folder
from moontransfer.files import (
    DestinationCheck,
    DestinationConflict,
    unique_destination_path,
)
from moontransfer.progress import format_file_size
from moontransfer.protocol import (
    ProtocolError,
    TransferProposal,
    validate_croc_code,
)
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

        self.status_label = StatusLabel("Pronto a inviare un file.")
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Seleziona un file da inviare")
        self.browse_button = QPushButton("Sfoglia...")
        self.file_info_label = QLabel("Nessun file selezionato.")
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

        file_row = QHBoxLayout()
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(self.browse_button)

        control_row = QHBoxLayout()
        control_row.addWidget(self.start_button)
        control_row.addWidget(self.stop_button)
        control_row.addStretch(1)
        control_row.addWidget(QLabel("Codice:"))
        control_row.addWidget(self.code_edit, 1)
        control_row.addWidget(self.copy_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addLayout(file_row)
        layout.addWidget(self.file_info_label)
        layout.addLayout(control_row)
        layout.addWidget(self.progress)
        add_expandable_output(layout, self.output)

        self.browse_button.clicked.connect(self._browse_file)
        self.file_edit.textChanged.connect(self._refresh_file_info)
        self.start_button.clicked.connect(self._start_send)
        self.stop_button.clicked.connect(self._stop_send)
        self.copy_button.clicked.connect(self._copy_code)
        self._refresh_file_info()

    def stop_active_transfers(self) -> None:
        self.controller.stop()

    def _make_runner(self, croc_path: str) -> CrocRunner:
        return CrocRunner(
            croc_path,
            append_text=self.terminal.append_text,
            append_line=self.terminal.append_line,
        )

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona file da inviare",
            str(Path.home()),
        )
        if path:
            self.file_edit.setText(path)
            self._refresh_file_info()

    def _selected_file(self) -> Path | None:
        path_text = self.file_edit.text().strip()
        if not path_text:
            return None
        return Path(path_text)

    def _has_valid_file(self) -> bool:
        path = self._selected_file()
        return bool(path and path.is_file())

    def _refresh_file_info(self) -> None:
        path = self._selected_file()
        if not path:
            self.file_info_label.setText("Nessun file selezionato.")
            self.start_button.setEnabled(False)
            self.progress.set_total_preview(None)
            return

        if not path.is_file():
            self.file_info_label.setText(
                "Il percorso selezionato non è un file valido."
            )
            self.start_button.setEnabled(False)
            self.progress.set_total_preview(None)
            return

        try:
            size_bytes = path.stat().st_size
            size = format_file_size(size_bytes)
        except OSError:
            size_bytes = None
            size = "dimensione non disponibile"

        self.file_info_label.setText(f"File: {path.name} - {size}")
        self.progress.set_total_preview(size_bytes)
        if not self.controller.active:
            self.start_button.setEnabled(True)
            self.status_label.setText(
                "File selezionato. Premi Invia per generare il codice."
            )

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(
            False if running else self._has_valid_file()
        )
        self.stop_button.setEnabled(running)
        self.browse_button.setEnabled(not running)
        self.file_edit.setEnabled(not running)
        self.copy_button.setEnabled(bool(self.last_code))

    def _set_code(self, code: str | None) -> None:
        self.last_code = code
        self.code_edit.setText(code or "")
        self.copy_button.setEnabled(bool(code))

    def _stop_send(self) -> None:
        self.controller.stop()

    def _start_send(self) -> None:
        path = self._selected_file()
        if not path or not path.is_file():
            self.status_label.setText(
                "Seleziona un file valido prima di inviare."
            )
            QMessageBox.warning(
                self,
                "File non valido",
                "Seleziona un file valido.",
            )
            return

        try:
            self.controller.start(path)
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
        answer_box = plain_message_box(
            self,
            icon=QMessageBox.Icon.Question,
            title="Accetta trasferimento",
            text=(
                f"{self._proposal_details(proposal)}\n\n"
                "Vuoi ricevere questo file?"
            ),
            standard_buttons=(
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
            default_button=QMessageBox.StandardButton.No,
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
        return (
            f"Nome: {proposal.filename}\n"
            f"Dimensione: {format_file_size(proposal.size)}\n"
            f"SHA-256: {proposal.sha256}"
        )


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MoonTransfer")
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
    app.setApplicationName("MoonTransfer")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
from moontransfer.messages import croc_status_from_line, process_result_message
from moontransfer.progress import (
    format_file_size,
    parse_announced_transfer_total,
    parse_transfer_progress,
)
from moontransfer.runner import CrocRunner
from moontransfer.widgets import (
    StatusLabel,
    TechnicalOutput,
    TransferProgressWidget,
    add_expandable_output,
)


class SendTab(QWidget):
    def __init__(self, croc_path: str) -> None:
        super().__init__()
        self.last_code: str | None = None

        self.status_label = StatusLabel("Pronto a inviare un file.")
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Seleziona un file da inviare")
        self.browse_button = QPushButton("Sfoglia...")
        self.file_info_label = QLabel("Nessun file selezionato.")
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
        self.runner = CrocRunner(
            croc_path,
            append_text=self.terminal.append_text,
            append_line=self.terminal.append_line,
        )
        self.runner.on_line = self._on_croc_line
        self.runner.on_finished = self._on_finished

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
            self.file_info_label.setText("Il percorso selezionato non è un file valido.")
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
        if not self.runner.is_running():
            self.start_button.setEnabled(True)
            self.status_label.setText("File selezionato. Premi Invia per generare il codice.")

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(False if running else self._has_valid_file())
        self.stop_button.setEnabled(running)
        self.browse_button.setEnabled(not running)
        self.file_edit.setEnabled(not running)

    def _stop_send(self) -> None:
        self.status_label.setText("Interruzione dell'invio in corso...")
        self.runner.stop()

    def _start_send(self) -> None:
        path = self._selected_file()

        if not path or not path.is_file():
            self.status_label.setText("Seleziona un file valido prima di inviare.")
            QMessageBox.warning(self, "File non valido", "Seleziona un file valido.")
            return

        self._refresh_file_info()
        try:
            total_bytes = path.stat().st_size
        except OSError:
            total_bytes = None

        self.last_code = None
        self.code_edit.clear()
        self.copy_button.setEnabled(False)
        self.progress.start(
            total_bytes=total_bytes,
            exact_total=total_bytes is not None,
        )
        self.status_label.setText("Invio avviato. Attendo il codice generato da croc...")

        args = croc.build_send_args(path)
        self._set_running(True)

        try:
            self.runner.start(args, unset_env=(croc.CROC_SECRET_ENV,))
        except Exception as exc:
            self._set_running(False)
            self.progress.finish(success=False)
            self.status_label.setText("Impossibile avviare l'invio.")
            QMessageBox.critical(self, "Errore avvio croc", str(exc))

    def _copy_code(self) -> None:
        if self.last_code:
            QApplication.clipboard().setText(self.last_code)
            self.status_label.setText("Codice copiato negli appunti.")
            self.terminal.append_line()
            self.terminal.append_line("[clipboard] codice copiato")

    def _on_croc_line(self, line: str) -> None:
        code = croc.parse_send_code(line)
        if code:
            self.last_code = code
            self.code_edit.setText(code)
            self.copy_button.setEnabled(True)

        status = croc_status_from_line(line, role="send")
        if status:
            self.status_label.setText(status)

        total = parse_announced_transfer_total(line)
        if total is not None:
            self.progress.set_total(total)

        sample = parse_transfer_progress(line)
        if sample:
            self.progress.apply_sample(sample)

    def _on_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self._set_running(False)
        success = exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0
        self.progress.finish(success=success)
        self.status_label.setText(
            process_result_message(
                action="Invio",
                exit_code=exit_code,
                crashed=exit_status == QProcess.ExitStatus.CrashExit,
            )
        )


class ReceiveTab(QWidget):
    def __init__(self, croc_path: str) -> None:
        super().__init__()
        self.croc_path = croc_path

        self.status_label = StatusLabel("Pronto a ricevere un file.")
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("Incolla il codice ricevuto")
        self.dest_edit = QLineEdit(str(Path.home() / "Downloads"))
        self.dest_button = QPushButton("Scegli...")
        self.open_dest_button = QPushButton("Apri cartella")
        self.overwrite_checkbox = QCheckBox("Consenti sovrascrittura")
        self.overwrite_checkbox.setToolTip(
            "Se nella cartella di destinazione esiste già un file con lo stesso "
            "nome, croc può sovrascriverlo durante la ricezione."
        )
        self.start_button = QPushButton("Ricevi")
        self.start_button.setEnabled(False)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)

        self.progress = TransferProgressWidget("Scaricato")
        self.output = TechnicalOutput()
        self.terminal = self.output.terminal
        self.runner = CrocRunner(
            croc_path,
            append_text=self.terminal.append_text,
            append_line=self.terminal.append_line,
        )
        self.runner.on_line = self._on_croc_line
        self.runner.on_finished = self._on_finished

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
        layout.addWidget(self.overwrite_checkbox)
        layout.addLayout(control_row)
        layout.addWidget(self.progress)
        add_expandable_output(layout, self.output)

        self.code_edit.textChanged.connect(self._refresh_receive_actions)
        self.dest_edit.textChanged.connect(self._refresh_receive_actions)
        self.overwrite_checkbox.toggled.connect(self._refresh_receive_actions)
        self.dest_button.clicked.connect(self._choose_destination)
        self.open_dest_button.clicked.connect(self._open_destination)
        self.start_button.clicked.connect(self._start_receive)
        self.stop_button.clicked.connect(self._stop_receive)
        self._refresh_receive_actions()

    def _choose_destination(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Scegli cartella di destinazione",
            self.dest_edit.text().strip() or str(Path.home()),
        )
        if path:
            self.dest_edit.setText(path)
            self.status_label.setText("Cartella di destinazione selezionata.")
            self._refresh_receive_actions()

    def _destination(self) -> Path:
        return Path(self.dest_edit.text().strip())

    def _can_open_destination(self) -> bool:
        destination_text = self.dest_edit.text().strip()
        return bool(destination_text and Path(destination_text).is_dir())

    def _can_start_receive(self) -> bool:
        return bool(
            self.code_edit.text().strip()
            and self.dest_edit.text().strip()
            and self.overwrite_checkbox.isChecked()
        )

    def _refresh_receive_actions(self) -> None:
        running = self.runner.is_running()
        self.start_button.setEnabled(not running and self._can_start_receive())
        self.open_dest_button.setEnabled(
            self._can_open_destination() and not running
        )

    def _open_destination(self) -> None:
        destination = self._destination()
        if not destination.is_dir():
            self.status_label.setText("La cartella di destinazione non esiste ancora.")
            QMessageBox.warning(
                self,
                "Cartella non disponibile",
                "La cartella di destinazione non esiste ancora.",
            )
            self._refresh_receive_actions()
            return

        result = open_folder(destination)
        if result.opened:
            self.status_label.setText("Cartella di destinazione aperta.")
        else:
            self.status_label.setText("Impossibile aprire la cartella di destinazione.")
            details = f"\n\nDettaglio tecnico:\n{result.error}" if result.error else ""
            QMessageBox.warning(
                self,
                "Apertura non riuscita",
                "Non riesco ad aprire la cartella con il file manager del sistema."
                + details,
            )

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(False if running else self._can_start_receive())
        self.stop_button.setEnabled(running)
        self.code_edit.setEnabled(not running)
        self.dest_edit.setEnabled(not running)
        self.dest_button.setEnabled(not running)
        self.overwrite_checkbox.setEnabled(not running)
        self.open_dest_button.setEnabled(not running and self._can_open_destination())

    def _stop_receive(self) -> None:
        self.status_label.setText("Interruzione della ricezione in corso...")
        self.runner.stop()

    def _start_receive(self) -> None:
        code = self.code_edit.text().strip()
        destination_text = self.dest_edit.text().strip()

        if not code:
            self.status_label.setText("Inserisci il codice ricevuto prima di avviare la ricezione.")
            QMessageBox.warning(self, "Codice mancante", "Incolla il codice ricevuto.")
            return

        if not destination_text:
            self.status_label.setText("Scegli una cartella di destinazione.")
            QMessageBox.warning(
                self,
                "Destinazione mancante",
                "Scegli una cartella di destinazione.",
            )
            return

        if not self.overwrite_checkbox.isChecked():
            self.status_label.setText("Conferma il comportamento di sovrascrittura prima di ricevere.")
            QMessageBox.warning(
                self,
                "Conferma sovrascrittura",
                "MoonTransfer usa croc in modalità automatica. Se nella cartella "
                "di destinazione esiste già un file con lo stesso nome, quel file "
                "può essere sovrascritto.",
            )
            return

        destination = Path(destination_text)

        try:
            destination.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Errore destinazione",
                f"Impossibile usare la cartella di destinazione:\n{exc}",
            )
            self.status_label.setText("Impossibile usare la cartella di destinazione.")
            self._refresh_receive_actions()
            return

        self._refresh_receive_actions()
        args = croc.build_receive_args()
        preview = croc.build_receive_preview(self.croc_path, args)
        self._set_running(True)
        self.progress.start()
        self.status_label.setText("Ricezione avviata. Attendo il trasferimento da croc...")

        try:
            self.runner.start(
                args,
                workdir=destination,
                env=croc.build_receive_environment(code),
                preview=preview,
            )
        except Exception as exc:
            self._set_running(False)
            self.progress.finish(success=False)
            self.status_label.setText("Impossibile avviare la ricezione.")
            QMessageBox.critical(self, "Errore avvio croc", str(exc))

    def _on_croc_line(self, line: str) -> None:
        status = croc_status_from_line(line, role="receive")
        if status:
            self.status_label.setText(status)

        total = parse_announced_transfer_total(line)
        if total is not None:
            self.progress.set_total(total)

        sample = parse_transfer_progress(line)
        if sample:
            self.progress.apply_sample(sample)

    def _on_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self._set_running(False)
        self._refresh_receive_actions()
        success = exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0
        self.progress.finish(success=success)
        self.status_label.setText(
            process_result_message(
                action="Ricezione",
                exit_code=exit_code,
                crashed=exit_status == QProcess.ExitStatus.CrashExit,
            )
        )


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MoonTransfer")

        croc_path = croc.find_executable()
        if not croc_path:
            QMessageBox.critical(
                self,
                "croc non trovato",
                "Esegui prima: uv run python tools/fetch_croc.py",
            )
            raise SystemExit(1)

        tabs = QTabWidget()
        tabs.addTab(SendTab(croc_path), "Invia")
        tabs.addTab(ReceiveTab(croc_path), "Ricevi")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        self.resize(900, self.sizeHint().height())


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MoonTransfer")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()

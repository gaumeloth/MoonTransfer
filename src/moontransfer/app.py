from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from moontransfer import croc


class TerminalView(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        font = QFont("monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

    def append_text(self, text: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.insertPlainText(text)
        self.ensureCursorVisible()

    def append_line(self, text: str = "") -> None:
        self.append_text(text + "\n")


class CrocRunner:
    def __init__(self, croc_path: str, terminal: TerminalView) -> None:
        self.croc_path = croc_path
        self.terminal = terminal
        self.on_line: Callable[[str], None] | None = None
        self.on_finished: Callable[[int, QProcess.ExitStatus], None] | None = None
        self._stdout_buffer = b""
        self._stderr_buffer = b""

        self.proc = QProcess()
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.proc.started.connect(self._on_started)
        self.proc.readyReadStandardOutput.connect(self._on_stdout)
        self.proc.readyReadStandardError.connect(self._on_stderr)
        self.proc.finished.connect(self._on_finished)

    def is_running(self) -> bool:
        return self.proc.state() != QProcess.ProcessState.NotRunning

    def start(
        self,
        args: list[str],
        *,
        workdir: Path | None = None,
        env: dict[str, str] | None = None,
        unset_env: tuple[str, ...] = (),
        preview: str | None = None,
    ) -> None:
        if self.is_running():
            raise RuntimeError("croc è già in esecuzione")

        self._stdout_buffer = b""
        self._stderr_buffer = b""
        self.proc.setWorkingDirectory(str(workdir or Path.home()))

        process_env = QProcessEnvironment.systemEnvironment()
        for key in unset_env:
            process_env.remove(key)
        for key, value in (env or {}).items():
            process_env.insert(key, value)
        self.proc.setProcessEnvironment(process_env)

        self.terminal.append_line()
        self.terminal.append_line(
            f"$ {preview or croc.command_preview(self.croc_path, args)}"
        )

        self.proc.start(self.croc_path, args)
        if not self.proc.waitForStarted(3000):
            raise RuntimeError(self.proc.errorString())

    def stop(self) -> None:
        if not self.is_running():
            return

        self.terminal.append_line()
        self.terminal.append_line("[stop] termino croc...")
        self.proc.terminate()

        if not self.proc.waitForFinished(1500):
            self.terminal.append_line("[stop] terminazione forzata")
            self.proc.kill()

    def _on_started(self) -> None:
        self.terminal.append_line("[process] avviato")

    def _on_stdout(self) -> None:
        self._handle_chunk(bytes(self.proc.readAllStandardOutput()), "_stdout_buffer")

    def _on_stderr(self) -> None:
        self._handle_chunk(bytes(self.proc.readAllStandardError()), "_stderr_buffer")

    def _handle_chunk(self, data: bytes, buffer_name: str) -> None:
        if not data:
            return

        self.terminal.append_text(data.decode("utf-8", errors="replace"))

        buffered = getattr(self, buffer_name) + data
        lines = buffered.split(b"\n")
        setattr(self, buffer_name, lines[-1])

        for raw_line in lines[:-1]:
            self._emit_line(raw_line)

    def _emit_line(self, raw_line: bytes) -> None:
        if self.on_line:
            self.on_line(raw_line.decode("utf-8", errors="replace").rstrip("\r"))

    def _flush_buffers(self) -> None:
        for name in ("_stdout_buffer", "_stderr_buffer"):
            raw_line = getattr(self, name)
            if raw_line:
                setattr(self, name, b"")
                self._emit_line(raw_line)

    def _on_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self._flush_buffers()
        self.terminal.append_line()
        self.terminal.append_line(
            f"[process] terminato: exit_code={exit_code}, "
            f"exit_status={exit_status.name}"
        )

        if self.on_finished:
            self.on_finished(exit_code, exit_status)


class SendTab(QWidget):
    def __init__(self, croc_path: str) -> None:
        super().__init__()
        self.last_code: str | None = None

        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Seleziona un file da inviare")
        self.browse_button = QPushButton("Sfoglia...")
        self.start_button = QPushButton("Invia")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.code_label = QLabel("Codice: -")
        self.copy_button = QPushButton("Copia codice")
        self.copy_button.setEnabled(False)

        self.terminal = TerminalView()
        self.runner = CrocRunner(croc_path, self.terminal)
        self.runner.on_line = self._on_croc_line
        self.runner.on_finished = self._on_finished

        file_row = QHBoxLayout()
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(self.browse_button)

        control_row = QHBoxLayout()
        control_row.addWidget(self.start_button)
        control_row.addWidget(self.stop_button)
        control_row.addStretch(1)
        control_row.addWidget(self.code_label)
        control_row.addWidget(self.copy_button)

        layout = QVBoxLayout(self)
        layout.addLayout(file_row)
        layout.addLayout(control_row)
        layout.addWidget(self.terminal, 1)

        self.browse_button.clicked.connect(self._browse_file)
        self.start_button.clicked.connect(self._start_send)
        self.stop_button.clicked.connect(self.runner.stop)
        self.copy_button.clicked.connect(self._copy_code)

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona file da inviare",
            str(Path.home()),
        )
        if path:
            self.file_edit.setText(path)

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.browse_button.setEnabled(not running)
        self.file_edit.setEnabled(not running)

    def _start_send(self) -> None:
        path = Path(self.file_edit.text().strip())

        if not path.is_file():
            QMessageBox.warning(self, "File non valido", "Seleziona un file valido.")
            return

        self.last_code = None
        self.code_label.setText("Codice: -")
        self.copy_button.setEnabled(False)

        args = croc.build_send_args(path)
        self._set_running(True)

        try:
            self.runner.start(args, unset_env=(croc.CROC_SECRET_ENV,))
        except Exception as exc:
            self._set_running(False)
            QMessageBox.critical(self, "Errore avvio croc", str(exc))

    def _copy_code(self) -> None:
        if self.last_code:
            QApplication.clipboard().setText(self.last_code)
            self.terminal.append_line()
            self.terminal.append_line("[clipboard] codice copiato")

    def _on_croc_line(self, line: str) -> None:
        code = croc.parse_send_code(line)
        if not code:
            return

        self.last_code = code
        self.code_label.setText(f"Codice: {code}")
        self.copy_button.setEnabled(True)

    def _on_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self._set_running(False)


class ReceiveTab(QWidget):
    def __init__(self, croc_path: str) -> None:
        super().__init__()
        self.croc_path = croc_path

        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("Incolla il codice ricevuto")
        self.dest_edit = QLineEdit(str(Path.home() / "Downloads"))
        self.dest_button = QPushButton("Scegli...")
        self.start_button = QPushButton("Ricevi")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)

        self.terminal = TerminalView()
        self.runner = CrocRunner(croc_path, self.terminal)
        self.runner.on_finished = self._on_finished

        code_row = QHBoxLayout()
        code_row.addWidget(QLabel("Codice:"))
        code_row.addWidget(self.code_edit, 1)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Destinazione:"))
        dest_row.addWidget(self.dest_edit, 1)
        dest_row.addWidget(self.dest_button)

        control_row = QHBoxLayout()
        control_row.addWidget(self.start_button)
        control_row.addWidget(self.stop_button)
        control_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(code_row)
        layout.addLayout(dest_row)
        layout.addLayout(control_row)
        layout.addWidget(self.terminal, 1)

        self.dest_button.clicked.connect(self._choose_destination)
        self.start_button.clicked.connect(self._start_receive)
        self.stop_button.clicked.connect(self.runner.stop)

    def _choose_destination(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Scegli cartella di destinazione",
            self.dest_edit.text().strip() or str(Path.home()),
        )
        if path:
            self.dest_edit.setText(path)

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.code_edit.setEnabled(not running)
        self.dest_edit.setEnabled(not running)
        self.dest_button.setEnabled(not running)

    def _start_receive(self) -> None:
        code = self.code_edit.text().strip()
        destination_text = self.dest_edit.text().strip()

        if not code:
            QMessageBox.warning(self, "Codice mancante", "Incolla il codice ricevuto.")
            return

        if not destination_text:
            QMessageBox.warning(
                self,
                "Destinazione mancante",
                "Scegli una cartella di destinazione.",
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
            return

        args = croc.build_receive_args()
        preview = croc.build_receive_preview(self.croc_path, args)
        self._set_running(True)

        try:
            self.runner.start(
                args,
                workdir=destination,
                env=croc.build_receive_environment(code),
                preview=preview,
            )
        except Exception as exc:
            self._set_running(False)
            QMessageBox.critical(self, "Errore avvio croc", str(exc))

    def _on_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self._set_running(False)


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MoonTransfer")
        self.resize(950, 650)

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


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MoonTransfer")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()

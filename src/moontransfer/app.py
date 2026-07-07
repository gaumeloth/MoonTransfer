from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt
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


CODE_RE = re.compile(r"Code is:\s*(.+)\s*$")


def project_root_from_source() -> Path:
    """
    In sviluppo il file è:
      <root>/src/moontransfer/app.py

    Quindi:
      app.py -> moontransfer -> src -> root
    """
    return Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def pyinstaller_resource_dir() -> Path | None:
    """
    Quando PyInstaller esegue il programma, i file bundled sono esposti in
    sys._MEIPASS.

    Nel nostro caso croc sarà copiato nella root del bundle:
      sys._MEIPASS/croc
      sys._MEIPASS/croc.exe
    """
    value = getattr(sys, "_MEIPASS", None)
    if not value:
        return None
    return Path(value)


def find_croc_executable() -> str | None:
    """
    Ordine di risoluzione:

    1. bundle PyInstaller: sys._MEIPASS/croc(.exe)
    2. sviluppo: <root>/third_party/croc/croc(.exe)
    3. accanto al modulo Python
    4. PATH di sistema
    """
    exe_name = "croc.exe" if os.name == "nt" else "croc"

    candidates: list[Path] = []

    bundle_dir = pyinstaller_resource_dir()
    if bundle_dir:
        candidates.append(bundle_dir / exe_name)

    try:
        root = project_root_from_source()
        candidates.append(root / "third_party" / "croc" / exe_name)
    except Exception:
        pass

    candidates.append(Path(__file__).resolve().parent / exe_name)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)

    return shutil.which(exe_name)


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

    def append_line(self, text: str) -> None:
        self.append_text(text + "\n")


class CrocRunner:
    """
    Wrapper minimale intorno a QProcess.

    Non interpreta davvero la progress bar di croc.
    Si limita a:
      - lanciare croc
      - streammare stdout/stderr
      - notificare le linee lette
      - notificare la fine processo
    """

    def __init__(self, croc_path: str, terminal: TerminalView) -> None:
        self.croc_path = croc_path
        self.terminal = terminal

        self.proc = QProcess()
        self.proc.setProcessChannelMode(
            QProcess.ProcessChannelMode.SeparateChannels)

        self.proc.started.connect(self._on_started)
        self.proc.readyReadStandardOutput.connect(self._on_stdout)
        self.proc.readyReadStandardError.connect(self._on_stderr)
        self.proc.finished.connect(self._on_finished)

        self.on_line = None
        self.on_finished = None

        self._stdout_buffer = b""
        self._stderr_buffer = b""

    def is_running(self) -> bool:
        return self.proc.state() != QProcess.ProcessState.NotRunning

    def start(
        self,
        args: list[str],
        *,
        workdir: str | None = None,
        extra_env: dict[str, str] | None = None,
        displayed_command: str | None = None,
    ) -> None:
        if self.is_running():
            raise RuntimeError("Processo croc già in esecuzione")

        self._stdout_buffer = b""
        self._stderr_buffer = b""

        if workdir:
            self.proc.setWorkingDirectory(workdir)
        else:
            self.proc.setWorkingDirectory(str(Path.home()))

        env = QProcessEnvironment.systemEnvironment()

        if extra_env:
            for key, value in extra_env.items():
                env.insert(key, value)

        self.proc.setProcessEnvironment(env)

        if displayed_command is None:
            displayed_command = f"{self.croc_path} {' '.join(args)}"

        self.terminal.append_line("")
        self.terminal.append_line(f"$ {displayed_command}")
        self.proc.start(self.croc_path, args)

        if not self.proc.waitForStarted(3000):
            raise RuntimeError("Impossibile avviare croc")

    def stop(self) -> None:
        if not self.is_running():
            return

        self.terminal.append_line("")
        self.terminal.append_line("[stop] termino il processo croc...")

        self.proc.terminate()

        if not self.proc.waitForFinished(1500):
            self.terminal.append_line("[stop] terminazione forzata")
            self.proc.kill()

    def _on_started(self) -> None:
        self.terminal.append_line("[process] avviato")

    def _decode(self, data: bytes) -> str:
        return data.decode("utf-8", errors="replace")

    def _emit_complete_lines(self, data: bytes, buffer_name: str) -> None:
        previous = getattr(self, buffer_name)
        combined = previous + data

        lines = combined.split(b"\n")
        setattr(self, buffer_name, lines[-1])

        for raw_line in lines[:-1]:
            line = self._decode(raw_line).rstrip("\r")
            if self.on_line:
                self.on_line(line)

    def _on_stdout(self) -> None:
        data = bytes(self.proc.readAllStandardOutput())
        if not data:
            return

        self.terminal.append_text(self._decode(data))
        self._emit_complete_lines(data, "_stdout_buffer")

    def _on_stderr(self) -> None:
        data = bytes(self.proc.readAllStandardError())
        if not data:
            return

        self.terminal.append_text(self._decode(data))
        self._emit_complete_lines(data, "_stderr_buffer")

    def _flush_buffers_as_lines(self) -> None:
        for buffer_name in ("_stdout_buffer", "_stderr_buffer"):
            raw = getattr(self, buffer_name)
            if raw:
                line = self._decode(raw).rstrip("\r")
                setattr(self, buffer_name, b"")
                if self.on_line:
                    self.on_line(line)

    def _on_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self._flush_buffers_as_lines()

        self.terminal.append_line("")
        self.terminal.append_line(
            f"[process] terminato: exit_code={
                exit_code}, exit_status={exit_status.name}"
        )

        if self.on_finished:
            self.on_finished(exit_code, exit_status)


class SendTab(QWidget):
    def __init__(self, croc_path: str) -> None:
        super().__init__()

        self.croc_path = croc_path
        self.last_code: str | None = None

        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Seleziona un file da inviare")

        self.browse_button = QPushButton("Sfoglia…")
        self.start_button = QPushButton("Invia")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)

        self.code_label = QLabel("Codice: —")
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

        layout = QVBoxLayout()
        layout.addLayout(file_row)
        layout.addLayout(control_row)
        layout.addWidget(self.terminal, 1)

        self.setLayout(layout)

        self.browse_button.clicked.connect(self._browse_file)
        self.start_button.clicked.connect(self._start_send)
        self.stop_button.clicked.connect(self._stop)
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
        path_text = self.file_edit.text().strip()

        if not path_text:
            QMessageBox.warning(
                self,
                "File mancante",
                "Seleziona un file da inviare.",
            )
            return

        path = Path(path_text)

        if not path.exists() or not path.is_file():
            QMessageBox.warning(
                self,
                "File non valido",
                "Il percorso selezionato non è un file valido.",
            )
            return

        self.last_code = None
        self.code_label.setText("Codice: —")
        self.copy_button.setEnabled(False)

        args = [
            "--ignore-stdin",
            "--disable-clipboard",
            "send",
            str(path),
        ]

        self._set_running(True)

        try:
            self.runner.start(args)
        except Exception as exc:
            self._set_running(False)
            QMessageBox.critical(
                self,
                "Errore avvio croc",
                str(exc),
            )

    def _stop(self) -> None:
        self.runner.stop()

    def _copy_code(self) -> None:
        if not self.last_code:
            return

        QApplication.clipboard().setText(self.last_code)
        self.terminal.append_line("")
        self.terminal.append_line("[clipboard] codice copiato")

    def _on_croc_line(self, line: str) -> None:
        match = CODE_RE.search(line)
        if not match:
            return

        code = match.group(1).strip()
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
        self.code_edit.setPlaceholderText("Incolla qui il codice ricevuto")

        self.dest_edit = QLineEdit()
        self.dest_edit.setPlaceholderText("Cartella di destinazione")

        downloads_dir = Path.home() / "Downloads"
        self.dest_edit.setText(str(downloads_dir))

        self.dest_button = QPushButton("Scegli…")
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

        layout = QVBoxLayout()
        layout.addLayout(code_row)
        layout.addLayout(dest_row)
        layout.addLayout(control_row)
        layout.addWidget(self.terminal, 1)

        self.setLayout(layout)

        self.dest_button.clicked.connect(self._choose_destination)
        self.start_button.clicked.connect(self._start_receive)
        self.stop_button.clicked.connect(self._stop)

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
            QMessageBox.warning(
                self,
                "Codice mancante",
                "Incolla il codice ricevuto dall'altro computer.",
            )
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
                f"Impossibile creare/usare la cartella di destinazione:\n{
                    exc}",
            )
            return

        args = [
            "--ignore-stdin",
            "--yes",
            "--overwrite",
        ]

        displayed_command = f"{self.croc_path} --yes --overwrite"
        extra_env = {
            "CROC_SECRET": code,
        }

        self._set_running(True)

        try:
            self.runner.start(
                args,
                workdir=str(destination),
                extra_env=extra_env,
                displayed_command=displayed_command,
            )
        except Exception as exc:
            self._set_running(False)
            QMessageBox.critical(
                self,
                "Errore avvio croc",
                str(exc),
            )

    def _stop(self) -> None:
        self.runner.stop()

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

        croc_path = find_croc_executable()

        if not croc_path:
            QMessageBox.critical(
                self,
                "croc non trovato",
                (
                    "Non riesco a trovare il binario croc.\n\n"
                    "In sviluppo esegui prima:\n"
                    "  uv run python tools/fetch_croc.py\n\n"
                    "Oppure assicurati che croc sia disponibile nel PATH."
                ),
            )
            raise SystemExit(1)

        tabs = QTabWidget()
        tabs.addTab(SendTab(croc_path), "Invia")
        tabs.addTab(ReceiveTab(croc_path), "Ricevi")

        layout = QVBoxLayout()
        layout.addWidget(tabs)

        self.setLayout(layout)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MoonTransfer")
    app.setOrganizationName("MoonTransfer")

    window = MainWindow()
    window.show()

    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()

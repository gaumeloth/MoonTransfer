from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from moontransfer import croc


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SIZE_UNIT_RE = r"(?:[KMGTPE]i?B|[KMGTPE]?B)"
TOTAL_RE = re.compile(
    rf"\b(?:Sending|Receiving)(?:\s+\d+\s+files)?(?:\s+'.*?')?"
    rf"\s+\((?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{SIZE_UNIT_RE})\)",
    re.IGNORECASE,
)
TRANSFER_PROGRESS_RE = re.compile(
    rf"\(\s*"
    rf"(?P<transferred>\d+(?:\.\d+)?)\s*"
    rf"(?P<transferred_unit>{SIZE_UNIT_RE})?\s*/\s*"
    rf"(?P<total>\d+(?:\.\d+)?)\s*"
    rf"(?P<total_unit>{SIZE_UNIT_RE})"
    rf"(?:,\s*(?P<speed>\d+(?:\.\d+)?)\s*"
    rf"(?P<speed_unit>{SIZE_UNIT_RE}/s))?"
    rf"\s*\)",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"\b(?P<percent>\d{1,3})%")


@dataclass(frozen=True)
class TransferProgressSample:
    percent: int | None = None
    transferred_bytes: int | None = None
    total_bytes: int | None = None
    speed_bps: float | None = None


def format_file_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"

    size = float(num_bytes)
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}"

    return f"{size:.1f} PiB"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"

    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def format_transfer_rate(bytes_per_second: float | None) -> str:
    if bytes_per_second is None or bytes_per_second <= 0:
        return "-"
    return f"{format_file_size(int(bytes_per_second))}/s"


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def parse_size_value(value: str, unit: str) -> int:
    unit = unit.strip()
    binary_units = {
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "TiB": 1024**4,
        "PiB": 1024**5,
        "EiB": 1024**6,
    }
    decimal_units = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "PB": 1000**5,
        "EB": 1000**6,
    }

    multiplier = None
    for name, value_multiplier in binary_units.items():
        if unit.lower() == name.lower():
            multiplier = value_multiplier
            break

    if multiplier is None:
        multiplier = decimal_units.get(unit.upper())

    if not multiplier:
        raise ValueError(f"Unità dimensione non supportata: {unit}")

    return int(float(value) * multiplier)


def parse_announced_transfer_total(line: str) -> int | None:
    match = TOTAL_RE.search(strip_ansi(line))
    if not match:
        return None

    return parse_size_value(match.group("value"), match.group("unit"))


def parse_transfer_progress(line: str) -> TransferProgressSample | None:
    clean_line = strip_ansi(line).strip()
    match = TRANSFER_PROGRESS_RE.search(clean_line)
    if not match:
        return None

    percent_match = PERCENT_RE.search(clean_line)
    percent = None
    if percent_match:
        percent = max(0, min(100, int(percent_match.group("percent"))))

    total_unit = match.group("total_unit")
    transferred_unit = match.group("transferred_unit") or total_unit
    transferred_bytes = parse_size_value(
        match.group("transferred"),
        transferred_unit,
    )
    total_bytes = parse_size_value(match.group("total"), total_unit)

    speed_bps = None
    if match.group("speed") and match.group("speed_unit"):
        speed_unit = match.group("speed_unit").removesuffix("/s")
        speed_bps = float(parse_size_value(match.group("speed"), speed_unit))

    return TransferProgressSample(
        percent=percent,
        transferred_bytes=transferred_bytes,
        total_bytes=total_bytes,
        speed_bps=speed_bps,
    )


def split_process_records(buffered: bytes) -> tuple[list[bytes], bytes]:
    records = re.split(rb"[\r\n]", buffered)
    if buffered.endswith((b"\r", b"\n")):
        return records, b""

    return records[:-1], records[-1]


def process_result_message(
    *,
    action: str,
    exit_code: int,
    exit_status: QProcess.ExitStatus,
) -> str:
    if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
        return f"{action}: completato."

    if exit_status == QProcess.ExitStatus.CrashExit:
        return f"{action}: interrotto. Controlla l'output tecnico."

    return f"{action}: terminato con errore. Controlla l'output tecnico."


def croc_status_from_line(line: str, *, role: str) -> str | None:
    normalized = line.strip().lower()
    if not normalized:
        return None

    if "code is:" in normalized and role == "send":
        return "Codice generato. Comunicalo alla persona che deve ricevere il file."

    if "waiting" in normalized and any(
        word in normalized for word in ("receiver", "recipient", "peer")
    ):
        return "In attesa che il destinatario usi il codice."

    if any(word in normalized for word in ("connecting", "connected")):
        return "Connessione stabilita. Trasferimento in preparazione."

    if any(word in normalized for word in ("sending", "receiving", "transferring")):
        return "Trasferimento in corso."

    if any(word in normalized for word in ("error", "failed", "refused", "unable")):
        return "croc segnala un errore. Controlla i dettagli tecnici."

    return None


def folder_open_command(
    path: Path,
    *,
    platform_name: str = sys.platform,
    which: Callable[[str], str | None] = shutil.which,
) -> list[str] | None:
    if platform_name == "darwin":
        opener = which("open")
        return [opener or "open", str(path)]

    if platform_name.startswith(("linux", "freebsd", "openbsd", "netbsd")):
        for command in (("xdg-open",), ("gio", "open"), ("kde-open5",), ("kde-open",)):
            opener = which(command[0])
            if opener:
                return [opener, *command[1:], str(path)]

    return None


def external_process_environment(
    env: Mapping[str, str] | None = None,
    *,
    frozen: bool | None = None,
) -> dict[str, str]:
    clean_env = dict(os.environ if env is None else env)
    running_frozen = getattr(sys, "frozen", False) if frozen is None else frozen

    original_library_path = clean_env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original_library_path is not None:
        if original_library_path:
            clean_env["LD_LIBRARY_PATH"] = original_library_path
        else:
            clean_env.pop("LD_LIBRARY_PATH", None)
    elif running_frozen:
        clean_env.pop("LD_LIBRARY_PATH", None)

    if running_frozen:
        for key in (
            "QT_PLUGIN_PATH",
            "QML2_IMPORT_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
        ):
            clean_env.pop(key, None)

    return clean_env


@dataclass(frozen=True)
class FolderOpenResult:
    opened: bool
    error: str = ""


def _folder_open_error(command: list[str], exit_code: int, stderr: str) -> str:
    details = stderr.strip()
    if not details:
        details = f"{Path(command[0]).name} è terminato con codice {exit_code}."

    return details[:1200]


def open_folder(path: Path) -> FolderOpenResult:
    if not path.is_dir():
        return FolderOpenResult(False, "La cartella non esiste.")

    if sys.platform.startswith("win"):
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return FolderOpenResult(True)
        except OSError as exc:
            return FolderOpenResult(False, str(exc))

    command = folder_open_command(path)
    if not command:
        return FolderOpenResult(False, "Nessun comando di apertura disponibile.")

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=external_process_environment(),
            start_new_session=True,
        )
    except OSError as exc:
        return FolderOpenResult(False, str(exc))

    try:
        _, stderr = process.communicate(timeout=1.0)
    except subprocess.TimeoutExpired:
        if process.stderr:
            process.stderr.close()
        return FolderOpenResult(True)

    if process.returncode == 0:
        return FolderOpenResult(True)

    return FolderOpenResult(
        False,
        _folder_open_error(command, process.returncode or 1, stderr),
    )


class StatusLabel(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setWordWrap(True)
        self.setStyleSheet(
            "QLabel {"
            "padding: 6px;"
            "border: 1px solid #c8c8c8;"
            "border-radius: 4px;"
            "background: #f6f6f6;"
            "}"
        )


class TransferProgressWidget(QWidget):
    def __init__(self, transferred_title: str) -> None:
        super().__init__()
        self.transferred_title = transferred_title
        self.total_bytes: int | None = None
        self.transferred_bytes = 0
        self.percent: int | None = None
        self.speed_bps: float | None = None
        self.started_at: float | None = None
        self.elapsed_seconds = 0.0
        self.running = False
        self.exact_total = False

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.total_value = QLabel("-")
        self.transferred_value = QLabel("0 B")
        self.speed_value = QLabel("-")
        self.elapsed_value = QLabel("-")
        self.eta_value = QLabel("-")

        for label in (
            self.total_value,
            self.transferred_value,
            self.speed_value,
            self.elapsed_value,
            self.eta_value,
        ):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.addWidget(self.progress_bar, 0, 0, 1, 6)
        grid.addWidget(QLabel("Totale:"), 1, 0)
        grid.addWidget(self.total_value, 1, 1)
        grid.addWidget(QLabel(f"{self.transferred_title}:"), 1, 2)
        grid.addWidget(self.transferred_value, 1, 3)
        grid.addWidget(QLabel("Velocità:"), 1, 4)
        grid.addWidget(self.speed_value, 1, 5)
        grid.addWidget(QLabel("Tempo:"), 2, 0)
        grid.addWidget(self.elapsed_value, 2, 1)
        grid.addWidget(QLabel("Fine stimata:"), 2, 2)
        grid.addWidget(self.eta_value, 2, 3)
        grid.setColumnStretch(5, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh)
        self._refresh()

    def set_total_preview(self, total_bytes: int | None) -> None:
        if self.running:
            return

        self.total_bytes = total_bytes
        self.transferred_bytes = 0
        self.percent = 0 if total_bytes else None
        self.speed_bps = None
        self.exact_total = bool(total_bytes)
        self.elapsed_seconds = 0.0
        self.started_at = None
        self._refresh()

    def start(
        self,
        *,
        total_bytes: int | None = None,
        exact_total: bool = False,
    ) -> None:
        self.total_bytes = total_bytes
        self.transferred_bytes = 0
        self.percent = 0 if total_bytes else None
        self.speed_bps = None
        self.started_at = time.monotonic()
        self.elapsed_seconds = 0.0
        self.running = True
        self.exact_total = exact_total
        self.timer.start()
        self._refresh()

    def set_total(self, total_bytes: int) -> None:
        if self.exact_total and self.total_bytes:
            return

        self.total_bytes = total_bytes
        self._refresh()

    def apply_sample(self, sample: TransferProgressSample) -> None:
        if sample.percent is not None:
            self.percent = sample.percent

        if sample.total_bytes is not None:
            self.set_total(sample.total_bytes)

        if sample.speed_bps is not None:
            self.speed_bps = sample.speed_bps

        if sample.transferred_bytes is not None:
            if self.exact_total and self.total_bytes and sample.percent is not None:
                self.transferred_bytes = round(self.total_bytes * sample.percent / 100)
            else:
                self.transferred_bytes = sample.transferred_bytes
        elif sample.percent is not None and self.total_bytes:
            self.transferred_bytes = round(self.total_bytes * sample.percent / 100)

        if self.total_bytes is not None:
            self.transferred_bytes = min(self.transferred_bytes, self.total_bytes)

        self._refresh()

    def finish(self, *, success: bool) -> None:
        if self.started_at is not None:
            self.elapsed_seconds = time.monotonic() - self.started_at
        self.running = False
        self.timer.stop()

        if success and self.total_bytes is not None:
            self.transferred_bytes = self.total_bytes
            self.percent = 100

        self._refresh(success=success)

    def _current_elapsed(self) -> float | None:
        if self.started_at is None:
            return None
        if self.running:
            return time.monotonic() - self.started_at
        return self.elapsed_seconds

    def _estimated_remaining(self, elapsed: float | None) -> float | None:
        if not self.running or not self.total_bytes or self.transferred_bytes <= 0:
            return None

        remaining = self.total_bytes - self.transferred_bytes
        if remaining <= 0:
            return 0.0

        speed = self.speed_bps
        if not speed and elapsed and elapsed > 0:
            speed = self.transferred_bytes / elapsed

        if not speed or speed <= 0:
            return None

        return remaining / speed

    def _refresh(self, *, success: bool = False) -> None:
        elapsed = self._current_elapsed()

        if self.total_bytes:
            percent = self.percent
            if percent is None:
                percent = round(self.transferred_bytes * 100 / self.total_bytes)
            percent = max(0, min(100, percent))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
        elif self.running:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

        self.total_value.setText(
            format_file_size(self.total_bytes) if self.total_bytes else "-"
        )
        self.transferred_value.setText(format_file_size(self.transferred_bytes))
        self.speed_value.setText(format_transfer_rate(self.speed_bps))
        self.elapsed_value.setText(format_duration(elapsed))

        eta = self._estimated_remaining(elapsed)
        if success:
            self.eta_value.setText("Completato")
        else:
            self.eta_value.setText(format_duration(eta))


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


class TechnicalOutput(QWidget):
    expanded_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.toggle = QToolButton()
        self.toggle.setText("Dettagli tecnici")
        self.toggle.setCheckable(True)
        self.toggle.setAutoRaise(True)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.clear_button = QPushButton("Pulisci")
        self.clear_button.setVisible(False)

        self.terminal = TerminalView()
        self.terminal.setMinimumHeight(180)
        self.terminal.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.terminal.setVisible(False)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.addWidget(self.toggle)
        toggle_row.addStretch(1)
        toggle_row.addWidget(self.clear_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toggle_row)
        layout.addWidget(self.terminal, 1)

        self.clear_button.clicked.connect(self.terminal.clear)
        self.toggle.toggled.connect(self._set_expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.clear_button.setVisible(expanded)
        self.terminal.setVisible(expanded)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding if expanded else QSizePolicy.Policy.Fixed,
        )
        self.updateGeometry()
        self.expanded_changed.emit(expanded)


def add_expandable_output(layout: QVBoxLayout, output: TechnicalOutput) -> None:
    layout.addWidget(output)
    layout.addStretch(1)
    spacer_index = layout.count() - 1
    compact_height: int | None = None

    def update_stretch(expanded: bool) -> None:
        layout.setStretchFactor(output, 1 if expanded else 0)
        layout.setStretch(spacer_index, 0 if expanded else 1)
        QTimer.singleShot(0, sync_window_size)

    def sync_window_size() -> None:
        nonlocal compact_height
        window = output.window()
        if not window or window.isMaximized() or window.isFullScreen():
            return

        expanded = output.toggle.isChecked()
        target_height = window.sizeHint().height()
        if expanded:
            window.setMinimumHeight(window.minimumSizeHint().height())
            if compact_height is None:
                compact_height = window.height()
            if window.height() < target_height:
                window.resize(window.width(), target_height)
        else:
            target_height = compact_height or target_height
            if window.height() > target_height:
                window.resize(window.width(), target_height)
            QTimer.singleShot(
                0,
                lambda target_height=target_height: shrink_collapsed_window(
                    target_height
                ),
            )
            compact_height = target_height

    def shrink_collapsed_window(target_height: int) -> None:
        window = output.window()
        if (
            window
            and not output.toggle.isChecked()
            and not window.isMaximized()
            and not window.isFullScreen()
        ):
            window.setMinimumHeight(target_height)
            window.resize(window.width(), target_height)

    output.expanded_changed.connect(update_stretch)
    update_stretch(output.toggle.isChecked())


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
        complete_lines, remaining = split_process_records(buffered)
        setattr(self, buffer_name, remaining)

        for raw_line in complete_lines:
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
                exit_status=exit_status,
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
        self.runner = CrocRunner(croc_path, self.terminal)
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
                exit_status=exit_status,
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

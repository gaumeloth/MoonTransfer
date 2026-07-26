from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer

from moontransfer import croc


MAX_PROCESS_RECORD_BYTES = 64 * 1024
PROCESS_TERMINATE_TIMEOUT_MS = 1500


def split_process_records(buffered: bytes) -> tuple[list[bytes], bytes]:
    records = re.split(rb"[\r\n]", buffered)
    if buffered.endswith((b"\r", b"\n")):
        return records, b""

    return records[:-1], records[-1]


def redact_sensitive_text(text: str, sensitive_values: tuple[str, ...]) -> str:
    redacted = text
    for value in sorted(
        (value for value in sensitive_values if value),
        key=len,
        reverse=True,
    ):
        redacted = redacted.replace(value, "<hidden>")
    return redacted


class CrocRunner:
    def __init__(
        self,
        croc_path: str,
        *,
        append_text: Callable[[str], None],
        append_line: Callable[[str], None],
    ) -> None:
        self.croc_path = croc_path
        self.append_text = append_text
        self.append_line = append_line
        self.on_line: Callable[[str], None] | None = None
        self.on_finished: Callable[[int, QProcess.ExitStatus], None] | None = None
        self._stdout_buffer = b""
        self._stderr_buffer = b""
        self._sensitive_values: tuple[str, ...] = ()
        self._stopping = False

        self.proc = QProcess()
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.proc.started.connect(self._on_started)
        self.proc.readyReadStandardOutput.connect(self._on_stdout)
        self.proc.readyReadStandardError.connect(self._on_stderr)
        self.proc.finished.connect(self._on_finished)
        self._kill_timer = QTimer(self.proc)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._force_stop)

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
        sensitive_values: tuple[str, ...] = (),
    ) -> None:
        if self.is_running() or self._stopping:
            raise RuntimeError("croc è già in esecuzione o in arresto")

        self._stdout_buffer = b""
        self._stderr_buffer = b""
        self._sensitive_values = sensitive_values
        self.proc.setWorkingDirectory(str(workdir or Path.home()))

        process_env = QProcessEnvironment.systemEnvironment()
        for key in unset_env:
            process_env.remove(key)
        for key, value in (env or {}).items():
            process_env.insert(key, value)
        self.proc.setProcessEnvironment(process_env)

        self.append_line()
        self.append_line(f"$ {preview or croc.command_preview(self.croc_path, args)}")

        self.proc.start(self.croc_path, args)
        if not self.proc.waitForStarted(3000):
            self._sensitive_values = ()
            raise RuntimeError(self.proc.errorString())

    def stop(self) -> None:
        if not self.is_running() or self._stopping:
            return

        self._stopping = True
        self.append_line()
        self.append_line("[stop] termino croc...")
        self.proc.terminate()
        self._kill_timer.start(PROCESS_TERMINATE_TIMEOUT_MS)

    def _force_stop(self) -> None:
        if not self.is_running():
            return

        self.append_line("[stop] terminazione forzata")
        self.proc.kill()

    def write_stdin(self, text: str, *, close: bool = False) -> None:
        if not self.is_running():
            return

        self.proc.write(text.encode("utf-8"))
        self.proc.waitForBytesWritten(1000)
        if close:
            self.proc.closeWriteChannel()

    def _on_started(self) -> None:
        self.append_line("[process] avviato")

    def _on_stdout(self) -> None:
        self._handle_chunk(bytes(self.proc.readAllStandardOutput()), "_stdout_buffer")

    def _on_stderr(self) -> None:
        self._handle_chunk(bytes(self.proc.readAllStandardError()), "_stderr_buffer")

    def _handle_chunk(self, data: bytes, buffer_name: str) -> None:
        if not data:
            return

        buffered = getattr(self, buffer_name) + data
        complete_lines, remaining = split_process_records(buffered)
        while len(remaining) > MAX_PROCESS_RECORD_BYTES:
            complete_lines.append(remaining[:MAX_PROCESS_RECORD_BYTES])
            remaining = remaining[MAX_PROCESS_RECORD_BYTES:]
        setattr(self, buffer_name, remaining)

        for raw_line in complete_lines:
            self._display_line(raw_line)
            self._emit_line(raw_line)

    def _display_line(self, raw_line: bytes) -> None:
        text = raw_line.decode("utf-8", errors="replace").rstrip("\r")
        self.append_line(redact_sensitive_text(text, self._sensitive_values))

    def _emit_line(self, raw_line: bytes) -> None:
        if self.on_line:
            self.on_line(raw_line.decode("utf-8", errors="replace").rstrip("\r"))

    def _flush_buffers(self) -> None:
        for name in ("_stdout_buffer", "_stderr_buffer"):
            raw_line = getattr(self, name)
            if raw_line:
                setattr(self, name, b"")
                self._display_line(raw_line)
                self._emit_line(raw_line)

    def _on_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self._kill_timer.stop()
        self._stopping = False
        self._flush_buffers()
        self.append_line()
        self.append_line(
            f"[process] terminato: exit_code={exit_code}, "
            f"exit_status={exit_status.name}"
        )

        try:
            if self.on_finished:
                self.on_finished(exit_code, exit_status)
        finally:
            self._sensitive_values = ()

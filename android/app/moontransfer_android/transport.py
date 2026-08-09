from __future__ import annotations

import os
import queue
import re
import subprocess
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import BinaryIO

from moontransfer import croc
from moontransfer.cancellation import OperationCancelled


CROC_LIBRARY_NAME = "libcroc.so"
PROBE_TIMEOUT_SECONDS = 10.0
TERMINATE_TIMEOUT_SECONDS = 2.0
MAX_PROCESS_RECORD_BYTES = 64 * 1024
PROCESS_READ_BYTES = 16 * 1024
NON_ERROR_OUTPUT_PREFIXES = (
    "Code is:",
    "On the other computer run:",
    "(For Windows)",
    "(For Linux/macOS)",
    "Or receive in a browser:",
    "https://getcroc.com/?code=",
    "croc ",
    "CROC_SECRET=",
)


class CrocProbeError(RuntimeError):
    pass


class CrocProcessError(RuntimeError):
    pass


class CrocProcessTimeout(CrocProcessError):
    pass


@dataclass(frozen=True)
class CrocProbeResult:
    executable: Path
    version: str


@dataclass(frozen=True)
class CrocProcessResult:
    returncode: int
    output_tail: tuple[str, ...]
    stdout_tail: tuple[str, ...] = ()
    stderr_tail: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ProcessRecord:
    stream_name: str
    text: str


def croc_failure_detail(result: CrocProcessResult) -> str:
    for lines in (
        result.stdout_tail,
        result.stderr_tail,
        result.output_tail,
    ):
        for line in reversed(lines):
            detail = line.strip()
            if detail and not detail.startswith(NON_ERROR_OUTPUT_PREFIXES):
                return detail
    return "croc non ha restituito dettagli sull'errore"


def android_native_library_dir() -> Path:
    try:
        from moontransfer_android.android_runtime import (
            AndroidRuntimeError,
            android_context,
        )
    except ImportError as error:
        raise CrocProbeError("Runtime Android non disponibile.") from error

    try:
        context = android_context()
    except AndroidRuntimeError as error:
        raise CrocProbeError(str(error)) from error
    return Path(str(context.getApplicationInfo().nativeLibraryDir))


def resolve_croc_executable(native_library_dir: Path | None = None) -> Path:
    directory = native_library_dir or android_native_library_dir()
    executable = directory / CROC_LIBRARY_NAME
    if not executable.is_file():
        raise CrocProbeError(f"Binario croc non trovato: {executable}")
    if not os.access(executable, os.X_OK):
        raise CrocProbeError(f"Binario croc non eseguibile: {executable}")
    return executable


def _terminate_process(process: subprocess.Popen[object]) -> None:
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=TERMINATE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


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


class CrocProcessRunner:
    def __init__(
        self,
        executable: Path,
        *,
        process_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
    ) -> None:
        self.executable = executable
        self.process_factory = process_factory
        self._lock = Lock()
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def request_stop(self) -> None:
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            _terminate_process(process)

    def run(
        self,
        args: list[str],
        *,
        config_dir: Path,
        secret: str,
        workdir: Path | None = None,
        idle_timeout: float,
        cancel_requested: Callable[[], bool],
        on_line: Callable[[str], None] | None = None,
        stdin_data: bytes | None = None,
        process_guard: Callable[[], None] | None = None,
    ) -> CrocProcessResult:
        if idle_timeout <= 0:
            raise ValueError("Il timeout di inattività deve essere positivo.")

        environment = os.environ.copy()
        environment.pop(croc.CROC_SECRET_ENV, None)
        environment.update(
            croc.build_process_environment(config_dir, secret=secret)
        )

        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise CrocProcessError("Un processo croc è già in esecuzione.")
            try:
                process = self.process_factory(
                    [str(self.executable), *args],
                    stdin=(
                        subprocess.PIPE
                        if stdin_data is not None
                        else subprocess.DEVNULL
                    ),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(workdir) if workdir else None,
                    env=environment,
                    text=False,
                    bufsize=0,
                )
            except OSError as error:
                raise CrocProcessError(
                    f"Impossibile avviare croc: {error}"
                ) from error
            self._process = process

        if process.stdout is None or process.stderr is None:
            _terminate_process(process)
            self._clear_process(process)
            raise CrocProcessError("Impossibile leggere l'output di croc.")

        output_queue: queue.Queue[_ProcessRecord | object] = queue.Queue()
        stream_finished = object()
        last_activity = [time.monotonic()]
        sensitive_values = (secret,)

        def pump(stream_name: str, stream: BinaryIO) -> None:
            buffered = b""
            try:
                while True:
                    chunk = stream.read(PROCESS_READ_BYTES)
                    if not chunk:
                        break
                    last_activity[0] = time.monotonic()
                    buffered += chunk
                    records, buffered = split_process_records(buffered)
                    while len(buffered) > MAX_PROCESS_RECORD_BYTES:
                        records.append(buffered[:MAX_PROCESS_RECORD_BYTES])
                        buffered = buffered[MAX_PROCESS_RECORD_BYTES:]
                    for record in records:
                        if not record:
                            continue
                        output_queue.put(
                            _ProcessRecord(
                                stream_name,
                                record.decode("utf-8", errors="replace").rstrip(
                                    "\r"
                                ),
                            )
                        )
                if buffered:
                    output_queue.put(
                        _ProcessRecord(
                            stream_name,
                            buffered.decode("utf-8", errors="replace").rstrip(
                                "\r"
                            ),
                        )
                    )
            finally:
                output_queue.put(stream_finished)

        readers = (
            Thread(target=pump, args=("stdout", process.stdout), daemon=True),
            Thread(target=pump, args=("stderr", process.stderr), daemon=True),
        )
        for reader in readers:
            reader.start()

        output_tail: deque[str] = deque(maxlen=24)
        stdout_tail: deque[str] = deque(maxlen=24)
        stderr_tail: deque[str] = deque(maxlen=24)
        finished_streams = 0
        cancelled = False
        timed_out = False
        guard_error: Exception | None = None

        try:
            if stdin_data is not None:
                if process.stdin is None:
                    raise CrocProcessError(
                        "Impossibile comunicare la decisione a croc."
                    )
                try:
                    process.stdin.write(stdin_data)
                    process.stdin.flush()
                except (BrokenPipeError, OSError) as error:
                    if process.poll() is None:
                        raise CrocProcessError(
                            "Impossibile comunicare la decisione a croc."
                        ) from error
                finally:
                    process.stdin.close()

            while process.poll() is None or finished_streams < len(readers):
                try:
                    item = output_queue.get(timeout=0.05)
                except queue.Empty:
                    item = None

                if item is stream_finished:
                    finished_streams += 1
                elif isinstance(item, _ProcessRecord):
                    line = redact_sensitive_text(item.text, sensitive_values)
                    output_tail.append(line)
                    if item.stream_name == "stdout":
                        stdout_tail.append(line)
                    else:
                        stderr_tail.append(line)
                    if on_line:
                        on_line(line)

                if process.poll() is None and process_guard is not None:
                    try:
                        process_guard()
                    except Exception as error:
                        guard_error = error
                        _terminate_process(process)

                if process.poll() is None and cancel_requested():
                    cancelled = True
                    _terminate_process(process)
                elif (
                    process.poll() is None
                    and time.monotonic() - last_activity[0] > idle_timeout
                ):
                    timed_out = True
                    _terminate_process(process)

            for reader in readers:
                reader.join(timeout=TERMINATE_TIMEOUT_SECONDS)
        finally:
            if process.poll() is None:
                _terminate_process(process)
            process.stdout.close()
            process.stderr.close()
            self._clear_process(process)

        if cancelled or cancel_requested():
            raise OperationCancelled
        if guard_error is not None:
            raise guard_error
        if timed_out:
            raise CrocProcessTimeout(
                "croc non ha prodotto attività entro il tempo previsto."
            )
        return CrocProcessResult(
            returncode=int(process.returncode or 0),
            output_tail=tuple(output_tail),
            stdout_tail=tuple(stdout_tail),
            stderr_tail=tuple(stderr_tail),
        )

    def _clear_process(self, process: subprocess.Popen[bytes]) -> None:
        with self._lock:
            if self._process is process:
                self._process = None


def probe_croc(
    config_dir: Path,
    *,
    executable: Path | None = None,
    timeout: float = PROBE_TIMEOUT_SECONDS,
    process_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
) -> CrocProbeResult:
    croc_executable = executable or resolve_croc_executable()
    environment = os.environ.copy()
    environment.pop(croc.CROC_SECRET_ENV, None)
    environment.update(croc.build_process_environment(config_dir))

    try:
        process = process_factory(
            [str(croc_executable), "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
        )
    except OSError as error:
        raise CrocProbeError(f"Impossibile avviare croc: {error}") from error

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        _terminate_process(process)
        raise CrocProbeError("La verifica di croc ha superato il timeout.") from error

    output = "\n".join(part for part in (stdout, stderr) if part)
    if process.returncode != 0:
        detail = output.strip() or f"exit code {process.returncode}"
        raise CrocProbeError(f"Verifica di croc non riuscita: {detail}")

    version = croc.parse_version_output(output)
    if version is None:
        raise CrocProbeError("croc non ha restituito una versione riconoscibile.")
    return CrocProbeResult(executable=croc_executable, version=version)

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from threading import Lock
from typing import Any

from moontransfer.files import is_link_or_reparse
from moontransfer.progress import TransferProgressSample
from moontransfer.protocol import (
    TransferProposal,
    generate_session_id,
    validate_croc_code,
    validate_filename,
    validate_sha256,
)
from moontransfer_android.storage import StagedDocument


SERVICE_PROTOCOL_VERSION = 1
SERVICE_DIRECTORY_NAME = "transfer-service"
REQUEST_FILENAME = "request.json"
STATE_FILENAME = "state.json"
COMMAND_DIRECTORY_NAME = "commands"
RUNTIME_DIRECTORY_NAME = "runtime"
MAX_SERVICE_JSON_BYTES = 128 * 1024
MAX_DESTINATION_URI_CHARS = 8192
MIN_PROGRESS_WRITE_INTERVAL_SECONDS = 0.2
SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class TransferServiceError(RuntimeError):
    pass


class TransferServiceOperation(str, Enum):
    SEND = "send"
    RECEIVE = "receive"


class TransferServiceCommandName(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    CANCEL = "cancel"
    SAVE = "save"


@dataclass(frozen=True)
class TransferServiceRequest:
    version: int
    session_id: str
    operation: TransferServiceOperation
    metadata_code: str | None = None
    document_path: str | None = None
    staging_dir: str | None = None
    filename: str | None = None
    size: int | None = None


@dataclass(frozen=True)
class TransferServiceCommand:
    version: int
    session_id: str
    command: TransferServiceCommandName
    destination_uri: str | None = None


@dataclass(frozen=True)
class TransferSummary:
    filename: str
    size: int
    sha256: str | None
    is_single_file: bool


@dataclass(frozen=True)
class TransferServiceSnapshot:
    version: int
    revision: int
    session_id: str
    operation: TransferServiceOperation
    state: str
    status: str
    terminal: bool
    service_done: bool
    heartbeat_ns: int
    code: str | None = None
    proposal: TransferSummary | None = None
    progress: TransferProgressSample | None = None
    save_copied: int | None = None
    save_total: int | None = None
    command_error: str | None = None


def service_root(cache_root: Path) -> Path:
    return cache_root / SERVICE_DIRECTORY_NAME


def validate_service_session_id(value: str) -> str:
    if not SESSION_ID_RE.fullmatch(value):
        raise TransferServiceError("Identificatore della sessione non valido.")
    return value


def service_session_dir(cache_root: Path, session_id: str) -> Path:
    return service_root(cache_root) / validate_service_session_id(session_id)


def create_send_service_request(
    cache_root: Path,
    document: StagedDocument,
) -> TransferServiceRequest:
    relative_path = _relative_private_path(cache_root, document.path)
    relative_staging = _relative_private_path(cache_root, document.staging_dir)
    request = TransferServiceRequest(
        version=SERVICE_PROTOCOL_VERSION,
        session_id=generate_session_id(),
        operation=TransferServiceOperation.SEND,
        document_path=relative_path,
        staging_dir=relative_staging,
        filename=validate_filename(document.filename),
        size=_validate_size(document.size),
    )
    _create_service_session(cache_root, request)
    return request


def create_receive_service_request(
    cache_root: Path,
    metadata_code: str,
) -> TransferServiceRequest:
    request = TransferServiceRequest(
        version=SERVICE_PROTOCOL_VERSION,
        session_id=generate_session_id(),
        operation=TransferServiceOperation.RECEIVE,
        metadata_code=validate_croc_code(metadata_code),
    )
    _create_service_session(cache_root, request)
    return request


def read_service_request(
    cache_root: Path,
    session_id: str,
) -> TransferServiceRequest:
    session_dir = _validated_session_dir(cache_root, session_id)
    data = _read_json_object(session_dir / REQUEST_FILENAME)
    if data.get("version") != SERVICE_PROTOCOL_VERSION:
        raise TransferServiceError("Versione della richiesta non supportata.")
    if data.get("session_id") != session_id:
        raise TransferServiceError("La richiesta appartiene a un'altra sessione.")

    try:
        operation = TransferServiceOperation(data.get("operation"))
    except ValueError as error:
        raise TransferServiceError("Operazione del servizio non valida.") from error

    if operation is TransferServiceOperation.RECEIVE:
        code = data.get("metadata_code")
        if not isinstance(code, str):
            raise TransferServiceError("Codice di ricezione mancante.")
        return TransferServiceRequest(
            version=SERVICE_PROTOCOL_VERSION,
            session_id=session_id,
            operation=operation,
            metadata_code=validate_croc_code(code),
        )

    document_path = _read_relative_private_path(data.get("document_path"))
    staging_dir = _read_relative_private_path(data.get("staging_dir"))
    filename = data.get("filename")
    size = data.get("size")
    if not isinstance(filename, str):
        raise TransferServiceError("Nome del file da inviare mancante.")
    if not isinstance(size, int) or isinstance(size, bool):
        raise TransferServiceError("Dimensione del file da inviare non valida.")

    validated_size = _validate_size(size)

    return TransferServiceRequest(
        version=SERVICE_PROTOCOL_VERSION,
        session_id=session_id,
        operation=operation,
        document_path=document_path,
        staging_dir=staging_dir,
        filename=validate_filename(filename),
        size=validated_size,
    )


def staged_document_from_request(
    cache_root: Path,
    request: TransferServiceRequest,
) -> StagedDocument:
    if request.operation is not TransferServiceOperation.SEND:
        raise TransferServiceError("La richiesta non contiene un file da inviare.")
    if (
        request.document_path is None
        or request.staging_dir is None
        or request.filename is None
        or request.size is None
    ):
        raise TransferServiceError("Richiesta di invio incompleta.")
    document = _resolve_private_path(cache_root, request.document_path)
    staging = _resolve_private_path(cache_root, request.staging_dir)
    if document.parent != staging:
        raise TransferServiceError("Percorso di staging del file non coerente.")
    if document.name != validate_filename(request.filename):
        raise TransferServiceError("Nome del file in staging non coerente.")
    staging_stat = staging.lstat()
    if is_link_or_reparse(staging_stat) or not staging.is_dir():
        raise TransferServiceError("Directory di staging non valida.")
    document_stat = document.lstat()
    if is_link_or_reparse(document_stat) or not document.is_file():
        raise TransferServiceError("Il file in staging non è regolare.")
    if document_stat.st_size != request.size:
        raise TransferServiceError("Il file in staging è cambiato.")
    return StagedDocument(
        path=document,
        staging_dir=staging,
        filename=request.filename,
        size=request.size,
    )


def submit_service_command(
    cache_root: Path,
    session_id: str,
    command: TransferServiceCommandName,
    *,
    destination_uri: str | None = None,
) -> Path:
    session_dir = _validated_session_dir(cache_root, session_id)
    if command is TransferServiceCommandName.SAVE:
        destination_uri = _validate_destination_uri(destination_uri)
    elif destination_uri is not None:
        raise TransferServiceError("URI inatteso per il comando richiesto.")

    command_data = {
        "version": SERVICE_PROTOCOL_VERSION,
        "session_id": session_id,
        "command": command.value,
        "destination_uri": destination_uri,
    }
    commands = session_dir / COMMAND_DIRECTORY_NAME
    commands.mkdir(mode=0o700, exist_ok=True)
    filename = f"{time.time_ns():020d}-{secrets.token_hex(8)}.json"
    path = commands / filename
    _write_json_atomic(path, command_data)
    return path


def consume_service_commands(
    cache_root: Path,
    session_id: str,
) -> tuple[TransferServiceCommand, ...]:
    session_dir = _validated_session_dir(cache_root, session_id)
    commands_dir = session_dir / COMMAND_DIRECTORY_NAME
    if not commands_dir.is_dir():
        return ()

    commands: list[TransferServiceCommand] = []
    for path in sorted(commands_dir.glob("*.json")):
        try:
            data = _read_json_object(path)
            if data.get("version") != SERVICE_PROTOCOL_VERSION:
                raise TransferServiceError("Versione del comando non supportata.")
            if data.get("session_id") != session_id:
                raise TransferServiceError("Comando destinato a un'altra sessione.")
            try:
                command = TransferServiceCommandName(data.get("command"))
            except ValueError as error:
                raise TransferServiceError(
                    "Comando del servizio non valido."
                ) from error
            destination_uri = data.get("destination_uri")
            if command is TransferServiceCommandName.SAVE:
                destination_uri = _validate_destination_uri(destination_uri)
            elif destination_uri is not None:
                raise TransferServiceError("URI inatteso nel comando.")
            commands.append(
                TransferServiceCommand(
                    version=SERVICE_PROTOCOL_VERSION,
                    session_id=session_id,
                    command=command,
                    destination_uri=destination_uri,
                )
            )
        finally:
            path.unlink(missing_ok=True)
    return tuple(commands)


class TransferServiceStateStore:
    def __init__(
        self,
        cache_root: Path,
        request: TransferServiceRequest,
    ) -> None:
        self.path = service_session_dir(cache_root, request.session_id) / STATE_FILENAME
        self._lock = Lock()
        self._last_progress_write = 0.0
        self._last_save_progress_write = 0.0
        self._data: dict[str, Any] = {
            "version": SERVICE_PROTOCOL_VERSION,
            "revision": 0,
            "session_id": request.session_id,
            "operation": request.operation.value,
            "state": "preparing",
            "status": "Avvio del servizio di trasferimento...",
            "terminal": False,
            "service_done": False,
            "heartbeat_ns": time.time_ns(),
            "code": None,
            "proposal": None,
            "progress": None,
            "save_copied": None,
            "save_total": None,
            "command_error": None,
        }
        self._write_locked()

    def update(self, **changes: Any) -> None:
        unexpected = set(changes) - set(self._data)
        if unexpected:
            raise TransferServiceError(
                f"Campi di stato non supportati: {', '.join(sorted(unexpected))}."
            )
        with self._lock:
            self._data.update(changes)
            self._data["revision"] += 1
            self._data["heartbeat_ns"] = time.time_ns()
            self._write_locked()

    def heartbeat(self) -> None:
        self.update()

    def set_proposal(self, proposal: TransferProposal) -> None:
        summary = TransferSummary(
            filename=proposal.filename,
            size=proposal.size,
            sha256=proposal.sha256,
            is_single_file=proposal.is_single_file,
        )
        self.update(proposal=asdict(summary))

    def set_progress(self, sample: TransferProgressSample) -> None:
        now = time.monotonic()
        if (
            sample.percent != 100
            and now - self._last_progress_write
            < MIN_PROGRESS_WRITE_INTERVAL_SECONDS
        ):
            return
        self._last_progress_write = now
        self.update(progress=asdict(sample))

    def set_save_progress(self, copied: int, total: int) -> None:
        now = time.monotonic()
        if (
            copied != total
            and now - self._last_save_progress_write
            < MIN_PROGRESS_WRITE_INTERVAL_SECONDS
        ):
            return
        self._last_save_progress_write = now
        self.update(save_copied=copied, save_total=total)

    def _write_locked(self) -> None:
        _write_json_atomic(self.path, self._data)


def read_service_snapshot(
    cache_root: Path,
    session_id: str,
) -> TransferServiceSnapshot:
    session_dir = _validated_session_dir(cache_root, session_id)
    data = _read_json_object(session_dir / STATE_FILENAME)
    if data.get("version") != SERVICE_PROTOCOL_VERSION:
        raise TransferServiceError("Versione dello stato non supportata.")
    if data.get("session_id") != session_id:
        raise TransferServiceError("Stato appartenente a un'altra sessione.")
    try:
        operation = TransferServiceOperation(data.get("operation"))
    except ValueError as error:
        raise TransferServiceError("Operazione nello stato non valida.") from error

    state = data.get("state")
    status = data.get("status")
    revision = data.get("revision")
    heartbeat_ns = data.get("heartbeat_ns")
    if not isinstance(state, str) or not state:
        raise TransferServiceError("Stato del trasferimento non valido.")
    if not isinstance(status, str):
        raise TransferServiceError("Messaggio di stato non valido.")
    if not isinstance(revision, int) or revision < 0:
        raise TransferServiceError("Revisione dello stato non valida.")
    if not isinstance(heartbeat_ns, int) or heartbeat_ns <= 0:
        raise TransferServiceError("Heartbeat del servizio non valido.")

    proposal = _read_summary(data.get("proposal"))
    progress = _read_progress(data.get("progress"))
    terminal = data.get("terminal")
    service_done = data.get("service_done")
    if not isinstance(terminal, bool) or not isinstance(service_done, bool):
        raise TransferServiceError("Indicatore terminale del servizio non valido.")
    code = data.get("code")
    if code is not None:
        if not isinstance(code, str):
            raise TransferServiceError("Codice di invio non valido.")
        code = validate_croc_code(code)

    return TransferServiceSnapshot(
        version=SERVICE_PROTOCOL_VERSION,
        revision=revision,
        session_id=session_id,
        operation=operation,
        state=state,
        status=status,
        terminal=terminal,
        service_done=service_done,
        heartbeat_ns=heartbeat_ns,
        code=code,
        proposal=proposal,
        progress=progress,
        save_copied=_optional_nonnegative_int(data.get("save_copied")),
        save_total=_optional_nonnegative_int(data.get("save_total")),
        command_error=_optional_string(
            data.get("command_error"),
            "Errore del comando non valido.",
        ),
    )


def discover_service_snapshots(cache_root: Path) -> tuple[TransferServiceSnapshot, ...]:
    root = service_root(cache_root)
    if not root.is_dir():
        return ()
    snapshots: list[TransferServiceSnapshot] = []
    for candidate in root.iterdir():
        try:
            stat_result = candidate.lstat()
            if is_link_or_reparse(stat_result) or not candidate.is_dir():
                continue
            session_id = validate_service_session_id(candidate.name)
            snapshots.append(read_service_snapshot(cache_root, session_id))
        except (OSError, TransferServiceError):
            continue
    return tuple(sorted(snapshots, key=lambda item: item.heartbeat_ns, reverse=True))


def cleanup_service_session(cache_root: Path, session_id: str) -> None:
    session_dir = service_session_dir(cache_root, session_id)
    try:
        stat_result = session_dir.lstat()
    except FileNotFoundError:
        return
    if is_link_or_reparse(stat_result) or not session_dir.is_dir():
        raise TransferServiceError("Directory della sessione non valida.")
    shutil.rmtree(session_dir, ignore_errors=True)


def _create_service_session(
    cache_root: Path,
    request: TransferServiceRequest,
) -> None:
    root = service_root(cache_root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    session_dir = root / request.session_id
    session_dir.mkdir(mode=0o700)
    (session_dir / COMMAND_DIRECTORY_NAME).mkdir(mode=0o700)
    try:
        data = asdict(request)
        data["operation"] = request.operation.value
        _write_json_atomic(session_dir / REQUEST_FILENAME, data)
        TransferServiceStateStore(cache_root, request)
    except BaseException:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise


def _validated_session_dir(cache_root: Path, session_id: str) -> Path:
    path = service_session_dir(cache_root, session_id)
    try:
        stat_result = path.lstat()
    except FileNotFoundError as error:
        raise TransferServiceError("Sessione del servizio non trovata.") from error
    if is_link_or_reparse(stat_result) or not path.is_dir():
        raise TransferServiceError("Directory della sessione non valida.")
    return path


def _relative_private_path(cache_root: Path, path: Path) -> str:
    try:
        relative = path.resolve(strict=True).relative_to(
            cache_root.resolve(strict=True)
        )
    except (OSError, ValueError) as error:
        raise TransferServiceError(
            "Il file selezionato non appartiene alla cache privata."
        ) from error
    return _read_relative_private_path(relative.as_posix())


def _read_relative_private_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise TransferServiceError("Percorso privato non valido.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise TransferServiceError("Percorso privato non valido.")
    if path.as_posix() != value:
        raise TransferServiceError("Percorso privato non normalizzato.")
    return value


def _resolve_private_path(cache_root: Path, relative: str) -> Path:
    root = cache_root.resolve(strict=True)
    candidate = root / _read_relative_private_path(relative)
    try:
        stat_result = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise TransferServiceError("Percorso privato non valido.") from error
    if is_link_or_reparse(stat_result) or resolved != candidate:
        raise TransferServiceError("Percorso privato non valido.")
    return resolved


def _validate_size(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TransferServiceError("Dimensione del file non valida.")
    return value


def _validate_destination_uri(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("content://")
        or len(value) > MAX_DESTINATION_URI_CHARS
        or any(ord(character) < 32 for character in value)
    ):
        raise TransferServiceError("Destinazione Android non valida.")
    return value


def _read_summary(value: Any) -> TransferSummary | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TransferServiceError("Riepilogo del trasferimento non valido.")
    filename = value.get("filename")
    size = value.get("size")
    sha256 = value.get("sha256")
    is_single_file = value.get("is_single_file")
    if not isinstance(filename, str):
        raise TransferServiceError("Nome nel riepilogo non valido.")
    if not isinstance(size, int) or isinstance(size, bool):
        raise TransferServiceError("Dimensione nel riepilogo non valida.")
    if sha256 is not None:
        if not isinstance(sha256, str):
            raise TransferServiceError("Hash nel riepilogo non valido.")
        sha256 = validate_sha256(sha256)
    if not isinstance(is_single_file, bool):
        raise TransferServiceError("Tipo di contenuto nel riepilogo non valido.")
    return TransferSummary(
        filename=validate_filename(filename),
        size=_validate_size(size),
        sha256=sha256,
        is_single_file=is_single_file,
    )


def _read_progress(value: Any) -> TransferProgressSample | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TransferServiceError("Avanzamento del trasferimento non valido.")
    percent = _optional_nonnegative_int(value.get("percent"))
    if percent is not None and percent > 100:
        raise TransferServiceError("Percentuale di avanzamento non valida.")
    transferred = _optional_nonnegative_int(value.get("transferred_bytes"))
    total = _optional_nonnegative_int(value.get("total_bytes"))
    speed = value.get("speed_bps")
    if speed is not None:
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or speed < 0:
            raise TransferServiceError("Velocità del trasferimento non valida.")
        speed = float(speed)
    return TransferProgressSample(
        percent=percent,
        transferred_bytes=transferred,
        total_bytes=total,
        speed_bps=speed,
    )


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TransferServiceError("Valore numerico dello stato non valido.")
    return value


def _optional_string(value: Any, message: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TransferServiceError(message)
    return value


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        stat_result = path.lstat()
        if is_link_or_reparse(stat_result) or not path.is_file():
            raise TransferServiceError("File IPC del servizio non valido.")
        if stat_result.st_size > MAX_SERVICE_JSON_BYTES:
            raise TransferServiceError("File IPC del servizio troppo grande.")
        data = json.loads(path.read_text(encoding="utf-8"))
    except TransferServiceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TransferServiceError(
            f"File IPC del servizio non leggibile: {error}"
        ) from error
    if not isinstance(data, dict):
        raise TransferServiceError("Il file IPC del servizio non è un oggetto JSON.")
    return data


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    serialized = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(serialized) > MAX_SERVICE_JSON_BYTES:
        raise TransferServiceError("File IPC del servizio troppo grande.")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)

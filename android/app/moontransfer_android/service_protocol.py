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
    MAX_PAYLOAD_ROOTS,
    TransferProposal,
    generate_session_id,
    portable_name_key,
    validate_croc_code,
    validate_filename,
    validate_sha256,
)
from moontransfer_android.storage import StagedDocument, StagedSelection


SERVICE_PROTOCOL_VERSION = 1
SERVICE_DIRECTORY_NAME = "transfer-service"
REQUEST_FILENAME = "request.json"
STATE_FILENAME = "state.json"
COMMAND_DIRECTORY_NAME = "commands"
RUNTIME_DIRECTORY_NAME = "runtime"
MAX_SERVICE_JSON_BYTES = 128 * 1024
MAX_DESTINATION_URI_CHARS = 8192
MIN_PROGRESS_WRITE_INTERVAL_SECONDS = 0.2
ATOMIC_REPLACE_RETRY_SECONDS = 0.01
ATOMIC_REPLACE_TIMEOUT_SECONDS = 1.0
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
class StagedFileReference:
    document_path: str
    staging_dir: str
    filename: str
    size: int


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
    documents: tuple[StagedFileReference, ...] = ()


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
    roots: tuple[str, ...] = ()
    file_count: int = 0
    directory_count: int = 0


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
    selection: StagedSelection | StagedDocument,
) -> TransferServiceRequest:
    if isinstance(selection, StagedDocument):
        selection = StagedSelection((selection,))
    references = tuple(
        StagedFileReference(
            document_path=_relative_private_path(cache_root, document.path),
            staging_dir=_relative_private_path(
                cache_root,
                document.staging_dir,
            ),
            filename=validate_filename(document.filename),
            size=_validate_size(document.size),
        )
        for document in selection.documents
    )
    first = references[0]
    request = TransferServiceRequest(
        version=SERVICE_PROTOCOL_VERSION,
        session_id=generate_session_id(),
        operation=TransferServiceOperation.SEND,
        document_path=(first.document_path if len(references) == 1 else None),
        staging_dir=(first.staging_dir if len(references) == 1 else None),
        filename=(first.filename if len(references) == 1 else "MoonTransfer"),
        size=selection.total_size,
        documents=references,
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

    filename = data.get("filename")
    size = data.get("size")
    if not isinstance(filename, str):
        raise TransferServiceError("Nome del file da inviare mancante.")
    if not isinstance(size, int) or isinstance(size, bool):
        raise TransferServiceError("Dimensione del file da inviare non valida.")

    validated_filename = validate_filename(filename)
    validated_size = _validate_size(size)
    documents_data = data.get("documents")
    if documents_data is None:
        document_path = _read_relative_private_path(data.get("document_path"))
        staging_dir = _read_relative_private_path(data.get("staging_dir"))
        documents = (
            StagedFileReference(
                document_path=document_path,
                staging_dir=staging_dir,
                filename=validated_filename,
                size=validated_size,
            ),
        )
    else:
        documents = _read_staged_file_references(documents_data)
        expected_filename = (
            documents[0].filename if len(documents) == 1 else "MoonTransfer"
        )
        if validated_filename != expected_filename:
            raise TransferServiceError(
                "Riepilogo dei file staged non coerente."
            )
        if validated_size != sum(document.size for document in documents):
            raise TransferServiceError(
                "Dimensione totale dei file staged non coerente."
            )
        document_path = (
            documents[0].document_path if len(documents) == 1 else None
        )
        staging_dir = (
            documents[0].staging_dir if len(documents) == 1 else None
        )

    return TransferServiceRequest(
        version=SERVICE_PROTOCOL_VERSION,
        session_id=session_id,
        operation=operation,
        document_path=document_path,
        staging_dir=staging_dir,
        filename=validated_filename,
        size=validated_size,
        documents=documents,
    )


def staged_document_from_request(
    cache_root: Path,
    request: TransferServiceRequest,
) -> StagedDocument:
    selection = staged_selection_from_request(cache_root, request)
    if selection.count != 1:
        raise TransferServiceError(
            "La richiesta contiene più di un file staged."
        )
    return selection.documents[0]


def staged_selection_from_request(
    cache_root: Path,
    request: TransferServiceRequest,
) -> StagedSelection:
    if request.operation is not TransferServiceOperation.SEND:
        raise TransferServiceError("La richiesta non contiene file da inviare.")
    references = request.documents
    if not references:
        if (
            request.document_path is None
            or request.staging_dir is None
            or request.filename is None
            or request.size is None
        ):
            raise TransferServiceError("Richiesta di invio incompleta.")
        references = (
            StagedFileReference(
                document_path=request.document_path,
                staging_dir=request.staging_dir,
                filename=request.filename,
                size=request.size,
            ),
        )
    documents = tuple(
        _staged_document_from_reference(cache_root, reference)
        for reference in references
    )
    name_keys = tuple(
        portable_name_key(document.filename) for document in documents
    )
    if len(set(name_keys)) != len(name_keys):
        raise TransferServiceError(
            "I file staged hanno nomi incompatibili o duplicati."
        )
    return StagedSelection(documents)


def _staged_document_from_reference(
    cache_root: Path,
    reference: StagedFileReference,
) -> StagedDocument:
    if not reference.document_path or not reference.staging_dir:
        raise TransferServiceError("Richiesta di invio incompleta.")
    filename = validate_filename(reference.filename)
    size = _validate_size(reference.size)
    document = _resolve_private_path(cache_root, reference.document_path)
    staging = _resolve_private_path(cache_root, reference.staging_dir)
    if document.parent != staging:
        raise TransferServiceError("Percorso di staging del file non coerente.")
    if document.name != filename:
        raise TransferServiceError("Nome del file in staging non coerente.")
    staging_stat = staging.lstat()
    if is_link_or_reparse(staging_stat) or not staging.is_dir():
        raise TransferServiceError("Directory di staging non valida.")
    document_stat = document.lstat()
    if is_link_or_reparse(document_stat) or not document.is_file():
        raise TransferServiceError("Il file in staging non è regolare.")
    if document_stat.st_size != size:
        raise TransferServiceError("Il file in staging è cambiato.")
    return StagedDocument(
        path=document,
        staging_dir=staging,
        filename=filename,
        size=size,
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
            roots=proposal.roots,
            file_count=proposal.file_count,
            directory_count=proposal.directory_count,
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


def discover_service_requests(
    cache_root: Path,
) -> tuple[TransferServiceRequest, ...]:
    root = service_root(cache_root)
    if not root.is_dir():
        return ()
    requests: list[tuple[int, TransferServiceRequest]] = []
    for candidate in root.iterdir():
        try:
            stat_result = candidate.lstat()
            if is_link_or_reparse(stat_result) or not candidate.is_dir():
                continue
            session_id = validate_service_session_id(candidate.name)
            request = read_service_request(cache_root, session_id)
            requests.append((stat_result.st_mtime_ns, request))
        except (OSError, TransferServiceError):
            continue
    return tuple(
        request
        for _modified_ns, request in sorted(
            requests,
            key=lambda item: item[0],
            reverse=True,
        )
    )


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


def _read_staged_file_references(
    value: Any,
) -> tuple[StagedFileReference, ...]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > MAX_PAYLOAD_ROOTS
    ):
        raise TransferServiceError("Elenco dei file staged non valido.")
    references: list[StagedFileReference] = []
    for item in value:
        if not isinstance(item, dict):
            raise TransferServiceError("Riferimento a file staged non valido.")
        filename = item.get("filename")
        size = item.get("size")
        if not isinstance(filename, str):
            raise TransferServiceError("Nome del file staged non valido.")
        if not isinstance(size, int) or isinstance(size, bool):
            raise TransferServiceError(
                "Dimensione del file staged non valida."
            )
        references.append(
            StagedFileReference(
                document_path=_read_relative_private_path(
                    item.get("document_path")
                ),
                staging_dir=_read_relative_private_path(
                    item.get("staging_dir")
                ),
                filename=validate_filename(filename),
                size=_validate_size(size),
            )
        )
    name_keys = tuple(
        portable_name_key(reference.filename) for reference in references
    )
    if len(set(name_keys)) != len(name_keys):
        raise TransferServiceError(
            "I riferimenti staged hanno nomi incompatibili o duplicati."
        )
    return tuple(references)


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

    validated_filename = validate_filename(filename)
    roots_value = value.get("roots")
    file_count_value = value.get("file_count")
    directory_count_value = value.get("directory_count")
    if (
        roots_value is None
        and file_count_value is None
        and directory_count_value is None
    ):
        # Service protocol v1 snapshots created before multi-file support.
        roots = (validated_filename,)
        file_count = 1 if is_single_file else 0
        directory_count = 0 if is_single_file else 1
    else:
        if (
            not isinstance(roots_value, list)
            or not roots_value
            or len(roots_value) > MAX_PAYLOAD_ROOTS
        ):
            raise TransferServiceError("Radici nel riepilogo non valide.")
        validated_roots: list[str] = []
        for root in roots_value:
            if not isinstance(root, str):
                raise TransferServiceError(
                    "Nome di una radice nel riepilogo non valido."
                )
            validated_roots.append(validate_filename(root))
        roots = tuple(validated_roots)
        root_keys = tuple(portable_name_key(root) for root in roots)
        if len(set(root_keys)) != len(root_keys):
            raise TransferServiceError(
                "Radici duplicate o incompatibili nel riepilogo."
            )
        file_count = _summary_count(file_count_value, "file")
        directory_count = _summary_count(
            directory_count_value,
            "directory",
        )
        if file_count + directory_count == 0:
            raise TransferServiceError("Riepilogo del contenuto vuoto.")

    expected_filename = roots[0] if len(roots) == 1 else "MoonTransfer"
    if validated_filename != expected_filename:
        raise TransferServiceError("Nome e radici del riepilogo non coerenti.")
    if is_single_file and (
        len(roots) != 1 or file_count != 1 or directory_count != 0
    ):
        raise TransferServiceError("Tipo e conteggi del riepilogo non coerenti.")
    if not is_single_file and sha256 is not None:
        raise TransferServiceError("Hash inatteso per un contenuto multiplo.")
    return TransferSummary(
        filename=validated_filename,
        size=_validate_size(size),
        sha256=sha256,
        is_single_file=is_single_file,
        roots=roots,
        file_count=file_count,
        directory_count=directory_count,
    )


def _summary_count(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TransferServiceError(
            f"Conteggio {label} nel riepilogo non valido."
        )
    return value


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
        _replace_file_atomic(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _replace_file_atomic(
    source: Path,
    destination: Path,
    *,
    windows: bool | None = None,
) -> None:
    if windows is None:
        windows = os.name == "nt"
    deadline = time.monotonic() + ATOMIC_REPLACE_TIMEOUT_SECONDS
    while True:
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            # Windows readers do not necessarily share delete access, so a
            # concurrent JSON read can briefly block replacement of the file.
            if not windows or time.monotonic() >= deadline:
                raise
            time.sleep(ATOMIC_REPLACE_RETRY_SECONDS)

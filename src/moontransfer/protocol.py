from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any


PROTOCOL_VERSION = 2
LEGACY_PROTOCOL_VERSION = 1
HASH_ALGORITHM = "sha256"
MAX_CONTROL_FILE_BYTES = 4 * 1024 * 1024
MAX_FILENAME_CHARS = 255
MAX_FILENAME_UTF8_BYTES = 255
MAX_RELATIVE_PATH_CHARS = 4096
MAX_RELATIVE_PATH_UTF8_BYTES = 4096
MAX_PATH_COMPONENTS = 128
MAX_PAYLOAD_ROOTS = 256
MAX_PAYLOAD_ENTRIES = 10_000
MAX_TRANSFER_FILE_BYTES = (1 << 63) - 1

PROPOSAL_TYPE = "proposal"
ENTRY_FILE = "file"
ENTRY_DIRECTORY = "directory"
ENTRY_TYPES = frozenset({ENTRY_FILE, ENTRY_DIRECTORY})
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
WINDOWS_FORBIDDEN_CHARS = frozenset('<>:"/\\|?*')
WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CLOCK$",
        "CONIN$",
        "CONOUT$",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
        *(f"COM{index}" for index in "¹²³"),
        *(f"LPT{index}" for index in "¹²³"),
    }
)


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class PayloadEntry:
    path: str
    type: str
    size: int | None = None
    sha256: str | None = None

    @property
    def is_file(self) -> bool:
        return self.type == ENTRY_FILE

    @property
    def is_directory(self) -> bool:
        return self.type == ENTRY_DIRECTORY


@dataclass(frozen=True)
class TransferProposal:
    version: int
    type: str
    session_id: str
    roots: tuple[str, ...]
    entries: tuple[PayloadEntry, ...]
    total_size: int
    file_count: int
    directory_count: int
    hash_algorithm: str
    main_code: str

    @property
    def size(self) -> int:
        return self.total_size

    @property
    def filename(self) -> str:
        if len(self.roots) == 1:
            return self.roots[0]
        return "MoonTransfer"

    @property
    def is_single_file(self) -> bool:
        return (
            len(self.roots) == 1
            and len(self.entries) == 1
            and self.entries[0].is_file
            and self.entries[0].path == self.roots[0]
        )

    @property
    def sha256(self) -> str | None:
        if self.is_single_file:
            return self.entries[0].sha256
        return None

    @property
    def destination_name(self) -> str:
        return self.roots[0] if len(self.roots) == 1 else "MoonTransfer"

    @property
    def file_sizes(self) -> tuple[int, ...]:
        entries_by_path = {entry.path: entry for entry in self.entries}
        sizes: list[int] = []
        for root in self.roots:
            for path in sorted(
                (
                    entry_path
                    for entry_path in entries_by_path
                    if entry_path == root or entry_path.startswith(f"{root}/")
                )
            ):
                entry = entries_by_path[path]
                if entry.is_file and entry.size is not None:
                    sizes.append(entry.size)
        return tuple(sizes)


def generate_croc_code() -> str:
    return secrets.token_hex(16)


def code_id(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]


def generate_session_id() -> str:
    return secrets.token_hex(16)


def validate_filename(filename: str) -> str:
    if not filename or filename in {".", ".."}:
        raise ProtocolError("Nome file mancante o non valido.")

    if "/" in filename or "\\" in filename:
        raise ProtocolError("Il nome file non deve contenere percorsi.")

    if Path(filename).name != filename:
        raise ProtocolError("Il nome file non deve contenere percorsi.")

    if len(filename) > MAX_FILENAME_CHARS:
        raise ProtocolError("Nome file troppo lungo.")

    try:
        encoded_filename = filename.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ProtocolError("Il nome file contiene caratteri Unicode non validi.") from exc

    if len(encoded_filename) > MAX_FILENAME_UTF8_BYTES:
        raise ProtocolError("Nome file troppo lungo.")

    if filename.endswith((" ", ".")):
        raise ProtocolError("Il nome file non può terminare con spazi o punti.")

    if any(character in WINDOWS_FORBIDDEN_CHARS for character in filename):
        raise ProtocolError("Il nome file contiene caratteri non portabili.")

    if any(
        unicodedata.category(character) in {"Cc", "Cf"}
        for character in filename
    ):
        raise ProtocolError("Il nome file contiene caratteri di controllo.")

    windows_basename = filename.split(".", 1)[0].upper()
    if windows_basename in WINDOWS_RESERVED_NAMES:
        raise ProtocolError("Nome file riservato dal sistema operativo.")

    return filename


def portable_name_key(filename: str) -> str:
    return unicodedata.normalize("NFC", filename).casefold()


def validate_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolError("Percorso relativo mancante o non valido.")
    if "\\" in value or value.startswith("/"):
        raise ProtocolError("Percorso relativo non portabile.")
    if len(value) > MAX_RELATIVE_PATH_CHARS:
        raise ProtocolError("Percorso relativo troppo lungo.")

    try:
        encoded_path = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ProtocolError("Il percorso contiene caratteri Unicode non validi.") from exc
    if len(encoded_path) > MAX_RELATIVE_PATH_UTF8_BYTES:
        raise ProtocolError("Percorso relativo troppo lungo.")

    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) > MAX_PATH_COMPONENTS:
        raise ProtocolError("Percorso relativo non valido.")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ProtocolError("Percorso relativo non valido.")
    if path.as_posix() != value:
        raise ProtocolError("Percorso relativo non normalizzato.")

    for part in path.parts:
        validate_filename(part)
    return value


def portable_path_key(value: str) -> tuple[str, ...]:
    path = PurePosixPath(validate_relative_path(value))
    return tuple(portable_name_key(part) for part in path.parts)


def validate_sha256(value: str) -> str:
    if len(value) != 64:
        raise ProtocolError("Hash SHA-256 non valido.")

    try:
        int(value, 16)
    except ValueError as exc:
        raise ProtocolError("Hash SHA-256 non valido.") from exc

    return value.lower()


def validate_croc_code(value: str) -> str:
    if not TOKEN_RE.fullmatch(value):
        raise ProtocolError("Codice di trasferimento non valido.")
    return value


def create_payload_proposal(
    *,
    roots: tuple[str, ...],
    entries: tuple[PayloadEntry, ...],
) -> TransferProposal:
    validated_roots, validated_entries = _validate_payload(roots, entries)
    total_size, file_count, directory_count = _payload_totals(validated_entries)
    return TransferProposal(
        version=PROTOCOL_VERSION,
        type=PROPOSAL_TYPE,
        session_id=generate_session_id(),
        roots=validated_roots,
        entries=validated_entries,
        total_size=total_size,
        file_count=file_count,
        directory_count=directory_count,
        hash_algorithm=HASH_ALGORITHM,
        main_code=generate_croc_code(),
    )


def create_proposal(
    *,
    filename: str,
    size: int,
    sha256: str,
) -> TransferProposal:
    return create_payload_proposal(
        roots=(validate_filename(filename),),
        entries=(
            PayloadEntry(
                path=filename,
                type=ENTRY_FILE,
                size=size,
                sha256=sha256,
            ),
        ),
    )


def write_control_file(path: Path, message: object) -> None:
    serialized = json.dumps(
        asdict(message),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(serialized) > MAX_CONTROL_FILE_BYTES:
        raise ProtocolError("File di controllo troppo grande.")
    path.write_bytes(serialized)


def read_proposal(path: Path) -> TransferProposal:
    data = _read_control_json(path)
    version = data.get("version")
    if version == LEGACY_PROTOCOL_VERSION:
        return _read_legacy_proposal(data)
    if version != PROTOCOL_VERSION:
        raise ProtocolError("Versione protocollo non supportata.")
    if data.get("type") != PROPOSAL_TYPE:
        raise ProtocolError("Tipo messaggio non valido.")

    roots_data = data.get("roots")
    entries_data = data.get("entries")
    if not isinstance(roots_data, list) or not isinstance(entries_data, list):
        raise ProtocolError("Manifest del trasferimento mancante o non valido.")

    roots = tuple(
        _validate_text("roots", root)
        for root in roots_data
    )
    entries = tuple(_read_payload_entry(entry) for entry in entries_data)
    validated_roots, validated_entries = _validate_payload(roots, entries)
    total_size, file_count, directory_count = _payload_totals(validated_entries)

    _expect_integer("total_size", data.get("total_size"), total_size)
    _expect_integer("file_count", data.get("file_count"), file_count)
    _expect_integer(
        "directory_count",
        data.get("directory_count"),
        directory_count,
    )

    hash_algorithm = _validate_text("hash_algorithm", data.get("hash_algorithm"))
    if hash_algorithm != HASH_ALGORITHM:
        raise ProtocolError("Algoritmo hash non supportato.")

    return TransferProposal(
        version=PROTOCOL_VERSION,
        type=PROPOSAL_TYPE,
        session_id=validate_croc_code(
            _validate_text("session_id", data.get("session_id"))
        ),
        roots=validated_roots,
        entries=validated_entries,
        total_size=total_size,
        file_count=file_count,
        directory_count=directory_count,
        hash_algorithm=hash_algorithm,
        main_code=validate_croc_code(
            _validate_text("main_code", data.get("main_code"))
        ),
    )


def _read_legacy_proposal(data: dict[str, Any]) -> TransferProposal:
    if data.get("type") != PROPOSAL_TYPE:
        raise ProtocolError("Tipo messaggio non valido.")

    filename = validate_filename(
        _validate_text("filename", data.get("filename"))
    )
    size = _validate_file_size(data.get("size"))
    hash_algorithm = _validate_text("hash_algorithm", data.get("hash_algorithm"))
    if hash_algorithm != HASH_ALGORITHM:
        raise ProtocolError("Algoritmo hash non supportato.")

    entry = PayloadEntry(
        path=filename,
        type=ENTRY_FILE,
        size=size,
        sha256=validate_sha256(
            _validate_text("sha256", data.get("sha256"))
        ),
    )
    return TransferProposal(
        version=LEGACY_PROTOCOL_VERSION,
        type=PROPOSAL_TYPE,
        session_id=validate_croc_code(
            _validate_text("session_id", data.get("session_id"))
        ),
        roots=(filename,),
        entries=(entry,),
        total_size=size,
        file_count=1,
        directory_count=0,
        hash_algorithm=hash_algorithm,
        main_code=validate_croc_code(
            _validate_text("main_code", data.get("main_code"))
        ),
    )


def _read_payload_entry(value: object) -> PayloadEntry:
    if not isinstance(value, dict):
        raise ProtocolError("Elemento del manifest non valido.")

    entry_type = _validate_text("type", value.get("type"))
    if entry_type == ENTRY_FILE:
        return PayloadEntry(
            path=_validate_text("path", value.get("path")),
            type=entry_type,
            size=_validate_file_size(value.get("size")),
            sha256=validate_sha256(
                _validate_text("sha256", value.get("sha256"))
            ),
        )
    if entry_type == ENTRY_DIRECTORY:
        if value.get("size") is not None or value.get("sha256") is not None:
            raise ProtocolError(
                "Una cartella non può avere dimensione o hash nel manifest."
            )
        return PayloadEntry(
            path=_validate_text("path", value.get("path")),
            type=entry_type,
        )
    raise ProtocolError("Tipo di elemento del manifest non supportato.")


def _validate_payload(
    roots: tuple[str, ...],
    entries: tuple[PayloadEntry, ...],
) -> tuple[tuple[str, ...], tuple[PayloadEntry, ...]]:
    if not roots or len(roots) > MAX_PAYLOAD_ROOTS:
        raise ProtocolError("Numero di elementi principali non valido.")
    if not entries or len(entries) > MAX_PAYLOAD_ENTRIES:
        raise ProtocolError("Numero di elementi del manifest non valido.")

    validated_roots = tuple(validate_filename(root) for root in roots)
    if len(set(validated_roots)) != len(validated_roots):
        raise ProtocolError("Elementi principali duplicati.")

    root_keys = [portable_name_key(root) for root in validated_roots]
    if len(set(root_keys)) != len(root_keys):
        raise ProtocolError(
            "I nomi principali entrano in conflitto su alcuni sistemi operativi."
        )

    validated_entries: list[PayloadEntry] = []
    paths: set[str] = set()
    portable_paths: set[tuple[str, ...]] = set()
    entry_types: dict[str, str] = {}
    roots_set = set(validated_roots)

    for entry in entries:
        if not isinstance(entry, PayloadEntry):
            raise ProtocolError("Elemento del manifest non valido.")
        path = validate_relative_path(entry.path)
        if path in paths:
            raise ProtocolError("Percorso duplicato nel manifest.")

        path_key = portable_path_key(path)
        if path_key in portable_paths:
            raise ProtocolError(
                "Percorsi in conflitto su alcuni sistemi operativi."
            )

        first_part = PurePosixPath(path).parts[0]
        if first_part not in roots_set:
            raise ProtocolError(
                "Un elemento del manifest non appartiene agli elementi principali."
            )

        if entry.type == ENTRY_FILE:
            validated_entry = PayloadEntry(
                path=path,
                type=ENTRY_FILE,
                size=_validate_file_size(entry.size),
                sha256=validate_sha256(
                    _validate_text("sha256", entry.sha256)
                ),
            )
        elif entry.type == ENTRY_DIRECTORY:
            if entry.size is not None or entry.sha256 is not None:
                raise ProtocolError(
                    "Una cartella non può avere dimensione o hash nel manifest."
                )
            validated_entry = PayloadEntry(path=path, type=ENTRY_DIRECTORY)
        else:
            raise ProtocolError("Tipo di elemento del manifest non supportato.")

        validated_entries.append(validated_entry)
        paths.add(path)
        portable_paths.add(path_key)
        entry_types[path] = entry.type

    for root in validated_roots:
        if root not in entry_types:
            raise ProtocolError("Elemento principale assente dal manifest.")

    for path in paths:
        parts = PurePosixPath(path).parts
        for index in range(1, len(parts)):
            parent = PurePosixPath(*parts[:index]).as_posix()
            if entry_types.get(parent) != ENTRY_DIRECTORY:
                raise ProtocolError(
                    "Cartella genitore assente o non valida nel manifest."
                )

    return validated_roots, tuple(
        sorted(validated_entries, key=lambda item: item.path)
    )


def _payload_totals(
    entries: tuple[PayloadEntry, ...],
) -> tuple[int, int, int]:
    total_size = 0
    file_count = 0
    directory_count = 0
    for entry in entries:
        if entry.is_file:
            assert entry.size is not None
            total_size += entry.size
            if total_size > MAX_TRANSFER_FILE_BYTES:
                raise ProtocolError("Dimensione totale del trasferimento non valida.")
            file_count += 1
        else:
            directory_count += 1
    return total_size, file_count, directory_count


def _validate_file_size(value: object) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or value > MAX_TRANSFER_FILE_BYTES
    ):
        raise ProtocolError("Dimensione file non valida.")
    return value


def _expect_integer(field: str, value: object, expected: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value != expected:
        raise ProtocolError(f"Campo {field} non coerente con il manifest.")


def _read_control_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_CONTROL_FILE_BYTES:
        raise ProtocolError("File di controllo troppo grande.")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("File di controllo JSON non valido.") from exc

    if not isinstance(data, dict):
        raise ProtocolError("File di controllo JSON non valido.")

    return data


def _validate_text(field: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolError(f"Campo {field} mancante o non valido.")

    return value

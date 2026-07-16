from __future__ import annotations

import json
import secrets
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = 1
HASH_ALGORITHM = "sha256"
MAX_CONTROL_FILE_BYTES = 64 * 1024

PROPOSAL_TYPE = "proposal"


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class TransferProposal:
    version: int
    type: str
    session_id: str
    filename: str
    size: int
    hash_algorithm: str
    sha256: str
    main_code: str


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

    return filename


def validate_sha256(value: str) -> str:
    if len(value) != 64:
        raise ProtocolError("Hash SHA-256 non valido.")

    try:
        int(value, 16)
    except ValueError as exc:
        raise ProtocolError("Hash SHA-256 non valido.") from exc

    return value.lower()


def create_proposal(
    *,
    filename: str,
    size: int,
    sha256: str,
) -> TransferProposal:
    if size < 0:
        raise ProtocolError("Dimensione file non valida.")

    return TransferProposal(
        version=PROTOCOL_VERSION,
        type=PROPOSAL_TYPE,
        session_id=generate_session_id(),
        filename=validate_filename(filename),
        size=size,
        hash_algorithm=HASH_ALGORITHM,
        sha256=validate_sha256(sha256),
        main_code=generate_croc_code(),
    )


def write_control_file(path: Path, message: object) -> None:
    path.write_text(
        json.dumps(asdict(message), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def read_proposal(path: Path) -> TransferProposal:
    data = _read_control_json(path)
    _expect_common(data, PROPOSAL_TYPE)

    filename = _validate_text("filename", data.get("filename"))
    size = data.get("size")
    if not isinstance(size, int) or size < 0:
        raise ProtocolError("Dimensione file non valida.")

    hash_algorithm = _validate_text("hash_algorithm", data.get("hash_algorithm"))
    if hash_algorithm != HASH_ALGORITHM:
        raise ProtocolError("Algoritmo hash non supportato.")

    return TransferProposal(
        version=PROTOCOL_VERSION,
        type=PROPOSAL_TYPE,
        session_id=_validate_text("session_id", data.get("session_id")),
        filename=validate_filename(filename),
        size=size,
        hash_algorithm=hash_algorithm,
        sha256=validate_sha256(_validate_text("sha256", data.get("sha256"))),
        main_code=_validate_text("main_code", data.get("main_code")),
    )


def _read_control_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_CONTROL_FILE_BYTES:
        raise ProtocolError("File di controllo troppo grande.")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProtocolError("File di controllo JSON non valido.") from exc

    if not isinstance(data, dict):
        raise ProtocolError("File di controllo JSON non valido.")

    return data


def _expect_common(data: dict[str, Any], expected_type: str) -> None:
    if data.get("version") != PROTOCOL_VERSION:
        raise ProtocolError("Versione protocollo non supportata.")

    if data.get("type") != expected_type:
        raise ProtocolError("Tipo messaggio non valido.")


def _validate_text(field: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolError(f"Campo {field} mancante o non valido.")

    return value

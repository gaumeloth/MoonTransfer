from __future__ import annotations

import errno
import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from moontransfer.protocol import TransferProposal


CONTROL_METADATA_NAME = "moontransfer-metadata.json"
CONTROL_DECISION_NAME = "moontransfer-decision.json"


class DestinationConflict(Enum):
    NONE = "none"
    IDENTICAL = "identical"
    DIFFERENT = "different"


@dataclass(frozen=True)
class DestinationCheck:
    conflict: DestinationConflict
    path: Path


@dataclass(frozen=True)
class SessionPaths:
    root: Path
    metadata_send: Path
    metadata_receive: Path
    decision_send: Path
    decision_receive: Path
    main_receive: Path


def create_session_paths() -> SessionPaths:
    root = Path(tempfile.mkdtemp(prefix="moontransfer-"))
    paths = SessionPaths(
        root=root,
        metadata_send=root / "metadata-send",
        metadata_receive=root / "metadata-receive",
        decision_send=root / "decision-send",
        decision_receive=root / "decision-receive",
        main_receive=root / "main-receive",
    )

    for directory in (
        paths.metadata_send,
        paths.metadata_receive,
        paths.decision_send,
        paths.decision_receive,
        paths.main_receive,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    return paths


def cleanup_session_paths(paths: SessionPaths | None) -> None:
    if paths:
        shutil.rmtree(paths.root, ignore_errors=True)


def reset_directory(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_destination(proposal: TransferProposal, destination_dir: Path) -> DestinationCheck:
    target = destination_dir / proposal.filename
    if not target.exists():
        return DestinationCheck(DestinationConflict.NONE, target)

    if not target.is_file():
        return DestinationCheck(DestinationConflict.DIFFERENT, target)

    try:
        if target.stat().st_size != proposal.size:
            return DestinationCheck(DestinationConflict.DIFFERENT, target)

        if sha256_file(target) == proposal.sha256:
            return DestinationCheck(DestinationConflict.IDENTICAL, target)
    except OSError:
        return DestinationCheck(DestinationConflict.DIFFERENT, target)

    return DestinationCheck(DestinationConflict.DIFFERENT, target)


def unique_destination_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    index = 1
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def received_path(directory: Path, filename: str) -> Path:
    return directory / filename


def verify_received_file(path: Path, proposal: TransferProposal) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"File ricevuto non trovato: {path}")

    size = path.stat().st_size
    if size != proposal.size:
        raise ValueError(
            f"Dimensione file non valida: atteso {proposal.size}, ricevuto {size}"
        )

    digest = sha256_file(path)
    if digest != proposal.sha256:
        raise ValueError("Hash SHA-256 del file ricevuto non corrispondente.")


def move_verified_file(source: Path, destination: Path, *, overwrite: bool) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        destination = unique_destination_path(destination)

    try:
        source.replace(destination)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        _copy_across_devices(source, destination)
    return destination


def _copy_across_devices(source: Path, destination: Path) -> None:
    temporary = tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.moontransfer-",
        dir=destination.parent,
        delete=False,
    )
    temporary_path = Path(temporary.name)
    temporary.close()

    try:
        shutil.copy2(source, temporary_path)
        temporary_path.replace(destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    try:
        source.unlink(missing_ok=True)
    except OSError:
        pass

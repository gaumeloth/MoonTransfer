from __future__ import annotations

import errno
import hashlib
import shutil
import stat
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from moontransfer.protocol import TransferProposal


CONTROL_METADATA_NAME = "moontransfer-metadata.json"


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
    croc_config: Path
    metadata_send: Path
    metadata_receive: Path
    main_receive: Path


def create_session_paths(
    *,
    main_receive_parent: Path | None = None,
) -> SessionPaths:
    root = Path(tempfile.mkdtemp(prefix="moontransfer-"))
    main_receive: Path | None = None
    try:
        if main_receive_parent is None:
            main_receive = root / "main-receive"
        else:
            main_receive_parent.mkdir(parents=True, exist_ok=True)
            main_receive = Path(
                tempfile.mkdtemp(
                    prefix=".moontransfer-receive-",
                    dir=main_receive_parent,
                )
            )

        paths = SessionPaths(
            root=root,
            croc_config=root / "croc-config",
            metadata_send=root / "metadata-send",
            metadata_receive=root / "metadata-receive",
            main_receive=main_receive,
        )

        for directory in (
            paths.croc_config,
            paths.metadata_send,
            paths.metadata_receive,
            paths.main_receive,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        return paths
    except Exception:
        if main_receive and main_receive.parent != root:
            shutil.rmtree(main_receive, ignore_errors=True)
        shutil.rmtree(root, ignore_errors=True)
        raise


def cleanup_session_paths(paths: SessionPaths | None) -> None:
    if paths:
        if paths.main_receive.parent != paths.root:
            shutil.rmtree(paths.main_receive, ignore_errors=True)
        shutil.rmtree(paths.root, ignore_errors=True)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_destination(proposal: TransferProposal, destination_dir: Path) -> DestinationCheck:
    target = destination_dir / proposal.filename
    if not target.exists() and not target.is_symlink():
        return DestinationCheck(DestinationConflict.NONE, target)

    try:
        if not stat.S_ISREG(target.lstat().st_mode):
            return DestinationCheck(DestinationConflict.DIFFERENT, target)
    except OSError:
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
    if not path.exists() and not path.is_symlink():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    index = 1
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        index += 1


def received_path(directory: Path, filename: str) -> Path:
    return directory / filename


def verify_received_file(path: Path, proposal: TransferProposal) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        raise FileNotFoundError(f"File ricevuto non trovato: {path}")

    if not stat.S_ISREG(mode):
        raise ValueError(f"Il file ricevuto non è un file regolare: {path}")

    size = path.stat().st_size
    if size != proposal.size:
        raise ValueError(
            f"Dimensione file non valida: atteso {proposal.size}, ricevuto {size}"
        )

    digest = sha256_file(path)
    if digest != proposal.sha256:
        raise ValueError("Hash SHA-256 del file ricevuto non corrispondente.")


def directory_payload_size(directory: Path) -> int:
    total = 0
    for path in directory.iterdir():
        try:
            item_stat = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(item_stat.st_mode):
            total += item_stat.st_size
        elif stat.S_ISDIR(item_stat.st_mode):
            try:
                total += directory_payload_size(path)
            except FileNotFoundError:
                continue
        else:
            raise ValueError(f"Elemento temporaneo non regolare: {path}")
    return total


def ensure_receive_capacity(
    directory: Path,
    required_bytes: int,
    *,
    reserve_bytes: int = 64 * 1024 * 1024,
) -> None:
    if required_bytes < 0:
        raise ValueError("Dimensione richiesta non valida.")

    free_bytes = shutil.disk_usage(directory).free
    if free_bytes < required_bytes + reserve_bytes:
        raise OSError(
            "Spazio libero insufficiente per ricevere il file "
            f"({free_bytes} byte disponibili, "
            f"{required_bytes + reserve_bytes} byte richiesti)."
        )


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

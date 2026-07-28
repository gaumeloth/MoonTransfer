from __future__ import annotations

import errno
import hashlib
import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from moontransfer.cancellation import OperationCancelled
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


@dataclass(frozen=True)
class FileFingerprint:
    size: int
    sha256: str
    device: int
    inode: int
    modified_ns: int


def is_link_or_reparse(item_stat: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(item_stat, "st_file_attributes", 0)
    return stat.S_ISLNK(item_stat.st_mode) or bool(
        reparse_flag and file_attributes & reparse_flag
    )


def path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


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


def sha256_file(
    path: Path,
    *,
    chunk_size: int = 1024 * 1024,
    cancel_requested: Callable[[], bool] | None = None,
) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            if cancel_requested and cancel_requested():
                raise OperationCancelled
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    if cancel_requested and cancel_requested():
        raise OperationCancelled
    return digest.hexdigest()


def fingerprint_file(
    path: Path,
    *,
    chunk_size: int = 1024 * 1024,
    cancel_requested: Callable[[], bool] | None = None,
) -> FileFingerprint:
    digest = hashlib.sha256()
    path_stat = path.lstat()
    if is_link_or_reparse(path_stat) or not stat.S_ISREG(path_stat.st_mode):
        raise OSError(f"Il percorso sorgente non è un file regolare: {path}")

    with path.open("rb") as source:
        initial = os.fstat(source.fileno())
        if not stat.S_ISREG(initial.st_mode):
            raise OSError(f"Il percorso sorgente non è un file regolare: {path}")

        while True:
            if cancel_requested and cancel_requested():
                raise OperationCancelled
            chunk = source.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
        final = os.fstat(source.fileno())

    if cancel_requested and cancel_requested():
        raise OperationCancelled

    current = path.lstat()
    identity_before = (
        initial.st_dev,
        initial.st_ino,
        initial.st_size,
        initial.st_mtime_ns,
    )
    identity_after = (
        final.st_dev,
        final.st_ino,
        final.st_size,
        final.st_mtime_ns,
    )
    identity_current = (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
    )
    if (
        is_link_or_reparse(current)
        or not stat.S_ISREG(current.st_mode)
        or identity_before != identity_after
        or identity_after != identity_current
    ):
        raise OSError(f"Il file è cambiato durante il calcolo dell'hash: {path}")

    return FileFingerprint(
        size=final.st_size,
        sha256=digest.hexdigest(),
        device=final.st_dev,
        inode=final.st_ino,
        modified_ns=final.st_mtime_ns,
    )


def ensure_file_unchanged(path: Path, fingerprint: FileFingerprint) -> None:
    current = path.lstat()
    identity = (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
    )
    expected = (
        fingerprint.device,
        fingerprint.inode,
        fingerprint.size,
        fingerprint.modified_ns,
    )
    if (
        identity != expected
        or is_link_or_reparse(current)
        or not stat.S_ISREG(current.st_mode)
    ):
        raise OSError(
            "Il file selezionato è cambiato dopo il calcolo dell'hash."
        )


def check_destination(
    proposal: TransferProposal,
    destination_dir: Path,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> DestinationCheck:
    target = destination_dir / proposal.filename
    if not path_entry_exists(target):
        return DestinationCheck(DestinationConflict.NONE, target)

    try:
        target_stat = target.lstat()
        if (
            is_link_or_reparse(target_stat)
            or not stat.S_ISREG(target_stat.st_mode)
        ):
            return DestinationCheck(DestinationConflict.DIFFERENT, target)
    except OSError:
        return DestinationCheck(DestinationConflict.DIFFERENT, target)

    try:
        if target_stat.st_size != proposal.size:
            return DestinationCheck(DestinationConflict.DIFFERENT, target)
        fingerprint = fingerprint_file(
            target,
            cancel_requested=cancel_requested,
        )
        if fingerprint.sha256 == proposal.sha256:
            return DestinationCheck(DestinationConflict.IDENTICAL, target)
    except OSError:
        return DestinationCheck(DestinationConflict.DIFFERENT, target)

    return DestinationCheck(DestinationConflict.DIFFERENT, target)


def unique_destination_path(path: Path) -> Path:
    if not path_entry_exists(path):
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    index = 1
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not path_entry_exists(candidate):
            return candidate
        index += 1


def unique_directory_path(path: Path) -> Path:
    if not path_entry_exists(path):
        return path

    index = 1
    while True:
        candidate = path.parent / f"{path.name} ({index})"
        if not path_entry_exists(candidate):
            return candidate
        index += 1


def received_path(directory: Path, filename: str) -> Path:
    return directory / filename


def verify_received_file(
    path: Path,
    proposal: TransferProposal,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> None:
    try:
        item_stat = path.lstat()
    except FileNotFoundError:
        raise FileNotFoundError(f"File ricevuto non trovato: {path}")

    if is_link_or_reparse(item_stat) or not stat.S_ISREG(item_stat.st_mode):
        raise ValueError(f"Il file ricevuto non è un file regolare: {path}")

    fingerprint = fingerprint_file(
        path,
        cancel_requested=cancel_requested,
    )
    if fingerprint.size != proposal.size:
        raise ValueError(
            "Dimensione file non valida: "
            f"atteso {proposal.size}, ricevuto {fingerprint.size}"
        )

    if fingerprint.sha256 != proposal.sha256:
        raise ValueError("Hash SHA-256 del file ricevuto non corrispondente.")


def directory_payload_size(directory: Path) -> int:
    total = 0
    for path in directory.iterdir():
        try:
            item_stat = path.lstat()
        except FileNotFoundError:
            continue
        if is_link_or_reparse(item_stat):
            raise ValueError(f"Elemento temporaneo non regolare: {path}")
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


def move_verified_file(
    source: Path,
    destination: Path,
    *,
    overwrite: bool,
    cancel_requested: Callable[[], bool] | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if path_entry_exists(destination) and not overwrite:
        destination = unique_destination_path(destination)

    if cancel_requested and cancel_requested():
        raise OperationCancelled

    try:
        if cancel_requested and cancel_requested():
            raise OperationCancelled
        source.replace(destination)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        _copy_across_devices(
            source,
            destination,
            cancel_requested=cancel_requested,
        )
    return destination


def _copy_across_devices(
    source: Path,
    destination: Path,
    *,
    cancel_requested: Callable[[], bool] | None = None,
    chunk_size: int = 1024 * 1024,
) -> None:
    temporary = tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.moontransfer-",
        dir=destination.parent,
        delete=False,
    )
    temporary_path = Path(temporary.name)
    temporary.close()

    try:
        with source.open("rb") as input_file, temporary_path.open("wb") as output_file:
            while True:
                if cancel_requested and cancel_requested():
                    raise OperationCancelled
                chunk = input_file.read(chunk_size)
                if not chunk:
                    break
                output_file.write(chunk)
        if cancel_requested and cancel_requested():
            raise OperationCancelled
        shutil.copystat(source, temporary_path)
        if cancel_requested and cancel_requested():
            raise OperationCancelled
        temporary_path.replace(destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    try:
        source.unlink(missing_ok=True)
    except OSError:
        pass

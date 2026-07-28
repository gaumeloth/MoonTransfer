from __future__ import annotations

import errno
import os
import shutil
import stat
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from moontransfer.cancellation import OperationCancelled
from moontransfer.files import (
    DestinationCheck,
    DestinationConflict,
    FileFingerprint,
    ensure_file_unchanged,
    fingerprint_file,
    is_link_or_reparse,
    move_verified_file,
    path_entry_exists,
    unique_directory_path,
)
from moontransfer.protocol import (
    ENTRY_DIRECTORY,
    ENTRY_FILE,
    MAX_PAYLOAD_ENTRIES,
    MAX_PAYLOAD_ROOTS,
    PayloadEntry,
    ProtocolError,
    TransferProposal,
    create_payload_proposal,
    portable_name_key,
    portable_path_key,
    validate_filename,
    validate_relative_path,
)


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative_path: str
    fingerprint: FileFingerprint


@dataclass(frozen=True)
class SourcePayload:
    root_paths: tuple[Path, ...]
    roots: tuple[str, ...]
    entries: tuple[PayloadEntry, ...]
    files: tuple[SourceFile, ...]

    @property
    def total_size(self) -> int:
        return sum(source.fingerprint.size for source in self.files)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def directory_count(self) -> int:
        return sum(entry.is_directory for entry in self.entries)

    def create_proposal(self) -> TransferProposal:
        return create_payload_proposal(
            roots=self.roots,
            entries=self.entries,
        )


def scan_source_payload(
    paths: Iterable[Path],
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> SourcePayload:
    roots = _normalize_source_roots(paths)
    entries: list[PayloadEntry] = []
    files: list[SourceFile] = []
    portable_paths: set[tuple[str, ...]] = set()

    def add_entry(entry: PayloadEntry) -> None:
        if len(entries) >= MAX_PAYLOAD_ENTRIES:
            raise ProtocolError(
                f"Il trasferimento supera il limite di {MAX_PAYLOAD_ENTRIES} elementi."
            )
        key = portable_path_key(entry.path)
        if key in portable_paths:
            raise ProtocolError(
                "Due percorsi entrano in conflitto su alcuni sistemi operativi: "
                f"{entry.path}"
            )
        portable_paths.add(key)
        entries.append(entry)

    def scan(path: Path, relative_path: str) -> None:
        _raise_if_cancelled(cancel_requested)
        item_stat = path.lstat()
        if is_link_or_reparse(item_stat):
            raise OSError(f"I collegamenti simbolici non sono supportati: {path}")

        if stat.S_ISREG(item_stat.st_mode):
            fingerprint = fingerprint_file(
                path,
                cancel_requested=cancel_requested,
            )
            current = path.lstat()
            if (
                is_link_or_reparse(current)
                or not stat.S_ISREG(current.st_mode)
                or current.st_dev != fingerprint.device
                or current.st_ino != fingerprint.inode
            ):
                raise OSError(
                    f"Il file è cambiato durante la preparazione: {path}"
                )
            add_entry(
                PayloadEntry(
                    path=relative_path,
                    type=ENTRY_FILE,
                    size=fingerprint.size,
                    sha256=fingerprint.sha256,
                )
            )
            files.append(
                SourceFile(
                    path=path,
                    relative_path=relative_path,
                    fingerprint=fingerprint,
                )
            )
            return

        if not stat.S_ISDIR(item_stat.st_mode):
            raise OSError(
                f"Il percorso non è un file o una cartella regolare: {path}"
            )

        add_entry(PayloadEntry(path=relative_path, type=ENTRY_DIRECTORY))
        try:
            children = _sorted_children(path)
        except OSError as exc:
            raise OSError(f"Impossibile leggere la cartella: {path}") from exc

        for child in children:
            validate_filename(child.name)
            child_relative = (
                PurePosixPath(relative_path) / child.name
            ).as_posix()
            scan(Path(child.path), child_relative)

    for root in roots:
        scan(root, root.name)

    _raise_if_cancelled(cancel_requested)
    proposal = create_payload_proposal(
        roots=tuple(root.name for root in roots),
        entries=tuple(entries),
    )
    files_by_path = {source.relative_path: source for source in files}
    ordered_files = tuple(
        files_by_path[entry.path]
        for entry in proposal.entries
        if entry.is_file
    )
    return SourcePayload(
        root_paths=roots,
        roots=proposal.roots,
        entries=proposal.entries,
        files=ordered_files,
    )


def ensure_source_payload_unchanged(
    payload: SourcePayload,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> None:
    expected_entries = {entry.path: entry for entry in payload.entries}
    expected_files = {
        source.relative_path: source
        for source in payload.files
    }
    seen: set[str] = set()

    def inspect(path: Path, relative_path: str) -> None:
        _raise_if_cancelled(cancel_requested)
        try:
            item_stat = path.lstat()
        except FileNotFoundError as exc:
            raise OSError(
                f"Un elemento selezionato non esiste più: {path}"
            ) from exc

        expected = expected_entries.get(relative_path)
        if expected is None:
            raise OSError(
                f"È stato aggiunto un elemento dopo la scansione: {path}"
            )

        if is_link_or_reparse(item_stat):
            raise OSError(
                f"Il tipo di un elemento selezionato è cambiato: {path}"
            )
        if stat.S_ISREG(item_stat.st_mode):
            if not expected.is_file:
                raise OSError(
                    f"Il tipo di un elemento selezionato è cambiato: {path}"
                )
            source = expected_files[relative_path]
            ensure_file_unchanged(path, source.fingerprint)
        elif stat.S_ISDIR(item_stat.st_mode):
            if not expected.is_directory:
                raise OSError(
                    f"Il tipo di un elemento selezionato è cambiato: {path}"
                )
            try:
                children = _sorted_children(path)
            except OSError as exc:
                raise OSError(f"Impossibile rileggere la cartella: {path}") from exc
            for child in children:
                child_relative = (
                    PurePosixPath(relative_path) / child.name
                ).as_posix()
                inspect(Path(child.path), child_relative)
        else:
            raise OSError(
                f"Il tipo di un elemento selezionato è cambiato: {path}"
            )

        seen.add(relative_path)

    for root in payload.root_paths:
        inspect(root, root.name)

    missing = set(expected_entries) - seen
    if missing:
        first = sorted(missing)[0]
        raise OSError(
            f"Un elemento selezionato è stato rimosso dopo la scansione: {first}"
        )
    _raise_if_cancelled(cancel_requested)


def check_payload_destination(
    proposal: TransferProposal,
    destination_dir: Path,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> DestinationCheck:
    target = destination_dir / proposal.destination_name
    if not path_entry_exists(target):
        return DestinationCheck(DestinationConflict.NONE, target)

    try:
        verify_existing_payload(
            target,
            proposal,
            cancel_requested=cancel_requested,
        )
    except OperationCancelled:
        raise
    except (OSError, ValueError):
        return DestinationCheck(DestinationConflict.DIFFERENT, target)
    return DestinationCheck(DestinationConflict.IDENTICAL, target)


def verify_existing_payload(
    target: Path,
    proposal: TransferProposal,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> None:
    if proposal.is_single_file:
        _verify_file(
            target,
            proposal.entries[0],
            cancel_requested=cancel_requested,
        )
        return

    target_stat = target.lstat()
    if not stat.S_ISDIR(target_stat.st_mode):
        raise ValueError(f"La destinazione esistente non è una cartella: {target}")

    if len(proposal.roots) == 1:
        root = proposal.roots[0]
        prefix = f"{root}/"
        expected = tuple(
            PayloadEntry(
                path=entry.path.removeprefix(prefix),
                type=entry.type,
                size=entry.size,
                sha256=entry.sha256,
            )
            for entry in proposal.entries
            if entry.path != root
        )
    else:
        expected = proposal.entries

    _verify_directory_contents(
        target,
        expected,
        cancel_requested=cancel_requested,
    )


def verify_received_payload(
    staging: Path,
    proposal: TransferProposal,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> None:
    staging_stat = staging.lstat()
    if not stat.S_ISDIR(staging_stat.st_mode):
        raise ValueError("La directory temporanea di ricezione non è valida.")
    _verify_directory_contents(
        staging,
        proposal.entries,
        cancel_requested=cancel_requested,
    )


def publish_received_payload(
    staging: Path,
    proposal: TransferProposal,
    target: Path,
    *,
    overwrite: bool,
    cancel_requested: Callable[[], bool] | None = None,
) -> Path:
    _raise_if_cancelled(cancel_requested)
    target.parent.mkdir(parents=True, exist_ok=True)

    if len(proposal.roots) == 1:
        source = staging / proposal.roots[0]
    else:
        source = staging

    if proposal.is_single_file:
        return move_verified_file(
            source,
            target,
            overwrite=overwrite,
            cancel_requested=cancel_requested,
        )

    if overwrite:
        raise ValueError(
            "La sovrascrittura o fusione di cartelle non è supportata."
        )
    if path_entry_exists(target):
        target = unique_directory_path(target)

    try:
        _raise_if_cancelled(cancel_requested)
        source.replace(target)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        _copy_directory_across_devices(
            source,
            target,
            cancel_requested=cancel_requested,
        )
    return target


def _normalize_source_roots(paths: Iterable[Path]) -> tuple[Path, ...]:
    candidates = tuple(Path(path).expanduser() for path in paths)
    if not candidates or len(candidates) > MAX_PAYLOAD_ROOTS:
        raise ProtocolError("Seleziona almeno un elemento da inviare.")

    normalized: list[Path] = []
    directory_roots: dict[Path, bool] = {}
    identities: set[str] = set()
    names: set[str] = set()
    for candidate in candidates:
        item_stat = candidate.lstat()
        if is_link_or_reparse(item_stat):
            raise OSError(
                f"I collegamenti simbolici non sono supportati: {candidate}"
            )
        if not stat.S_ISREG(item_stat.st_mode) and not stat.S_ISDIR(
            item_stat.st_mode
        ):
            raise OSError(
                f"Il percorso non è un file o una cartella regolare: {candidate}"
            )

        resolved = candidate.resolve(strict=True)
        identity = os.path.normcase(str(resolved))
        if identity in identities:
            continue

        validate_filename(resolved.name)
        name_key = portable_name_key(resolved.name)
        if name_key in names:
            raise ProtocolError(
                "Due elementi principali hanno nomi incompatibili: "
                f"{resolved.name}"
            )

        for existing in normalized:
            if (
                directory_roots[existing]
                and resolved.is_relative_to(existing)
            ) or (
                stat.S_ISDIR(item_stat.st_mode)
                and existing.is_relative_to(resolved)
            ):
                raise ProtocolError(
                    "Non selezionare separatamente una cartella e un suo contenuto."
                )

        identities.add(identity)
        names.add(name_key)
        normalized.append(resolved)
        directory_roots[resolved] = stat.S_ISDIR(item_stat.st_mode)

    return tuple(normalized)


def _verify_directory_contents(
    directory: Path,
    expected_entries: tuple[PayloadEntry, ...],
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> None:
    expected = {entry.path: entry for entry in expected_entries}
    seen: set[str] = set()

    def inspect(current: Path, relative_path: str) -> None:
        _raise_if_cancelled(cancel_requested)
        validated_path = validate_relative_path(relative_path)
        item = expected.get(validated_path)
        if item is None:
            raise ValueError(f"Elemento ricevuto non previsto: {relative_path}")

        item_stat = current.lstat()
        if is_link_or_reparse(item_stat):
            raise ValueError(
                f"Elemento ricevuto non regolare: {relative_path}"
            )
        if stat.S_ISREG(item_stat.st_mode):
            if not item.is_file:
                raise ValueError(
                    f"Tipo non corrispondente per l'elemento: {relative_path}"
                )
            _verify_file(
                current,
                item,
                cancel_requested=cancel_requested,
            )
        elif stat.S_ISDIR(item_stat.st_mode):
            if not item.is_directory:
                raise ValueError(
                    f"Tipo non corrispondente per l'elemento: {relative_path}"
                )
            try:
                children = _sorted_children(current)
            except OSError as exc:
                raise OSError(
                    f"Impossibile leggere l'elemento ricevuto: {current}"
                ) from exc
            for child in children:
                child_relative = (
                    PurePosixPath(relative_path) / child.name
                ).as_posix()
                inspect(Path(child.path), child_relative)
        else:
            raise ValueError(
                f"Elemento ricevuto non regolare: {relative_path}"
            )
        seen.add(validated_path)

    try:
        children = _sorted_children(directory)
    except OSError as exc:
        raise OSError(f"Impossibile leggere la cartella: {directory}") from exc
    for child in children:
        inspect(Path(child.path), child.name)

    missing = set(expected) - seen
    if missing:
        raise FileNotFoundError(
            f"Elemento atteso non ricevuto: {sorted(missing)[0]}"
        )
    _raise_if_cancelled(cancel_requested)


def _verify_file(
    path: Path,
    entry: PayloadEntry,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> None:
    if not entry.is_file or entry.size is None or entry.sha256 is None:
        raise ValueError("Voce file del manifest non valida.")

    fingerprint = fingerprint_file(
        path,
        cancel_requested=cancel_requested,
    )
    if fingerprint.size != entry.size:
        raise ValueError(
            f"Dimensione non valida per {entry.path}: "
            f"atteso {entry.size}, ricevuto {fingerprint.size}"
        )
    if fingerprint.sha256 != entry.sha256:
        raise ValueError(f"Hash SHA-256 non corrispondente per {entry.path}.")


def _copy_directory_across_devices(
    source: Path,
    destination: Path,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> None:
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.moontransfer-",
            dir=destination.parent,
        )
    )
    try:
        _copy_directory_contents(
            source,
            temporary,
            cancel_requested=cancel_requested,
        )
        _raise_if_cancelled(cancel_requested)
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    shutil.rmtree(source, ignore_errors=True)


def _copy_directory_contents(
    source: Path,
    destination: Path,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> None:
    for child in _sorted_children(source):
        _raise_if_cancelled(cancel_requested)
        child_path = Path(child.path)
        target = destination / child.name
        item_stat = child_path.lstat()
        if is_link_or_reparse(item_stat):
            raise ValueError(
                f"Elemento non regolare durante la copia: {child_path}"
            )
        if stat.S_ISDIR(item_stat.st_mode):
            target.mkdir()
            _copy_directory_contents(
                child_path,
                target,
                cancel_requested=cancel_requested,
            )
            shutil.copystat(child_path, target, follow_symlinks=False)
        elif stat.S_ISREG(item_stat.st_mode):
            _copy_regular_file(
                child_path,
                target,
                cancel_requested=cancel_requested,
            )
        else:
            raise ValueError(
                f"Elemento non regolare durante la copia: {child_path}"
            )


def _copy_regular_file(
    source: Path,
    destination: Path,
    *,
    cancel_requested: Callable[[], bool] | None = None,
    chunk_size: int = 1024 * 1024,
) -> None:
    with source.open("rb") as input_file, destination.open("xb") as output_file:
        while True:
            _raise_if_cancelled(cancel_requested)
            chunk = input_file.read(chunk_size)
            if not chunk:
                break
            output_file.write(chunk)
    shutil.copystat(source, destination, follow_symlinks=False)


def _raise_if_cancelled(
    cancel_requested: Callable[[], bool] | None,
) -> None:
    if cancel_requested and cancel_requested():
        raise OperationCancelled


def _sorted_children(path: Path) -> list[os.DirEntry[str]]:
    with os.scandir(path) as iterator:
        return sorted(iterator, key=lambda item: item.name)

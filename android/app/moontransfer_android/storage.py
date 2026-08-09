from __future__ import annotations

import errno
import mimetypes
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moontransfer.cancellation import OperationCancelled
from moontransfer.files import is_link_or_reparse
from moontransfer.protocol import (
    MAX_PAYLOAD_ROOTS,
    portable_name_key,
    validate_filename,
)


DISPLAY_NAME_COLUMN = "_display_name"
SIZE_COLUMN = "_size"
COPY_CHUNK_BYTES = 1024 * 1024
PICK_FILE_REQUEST_CODE = 0x4D54
SAVE_FILE_REQUEST_CODE = 0x4D55
SAVE_DIRECTORY_REQUEST_CODE = 0x4D56
DIRECTORY_MIME_TYPE = "vnd.android.document/directory"


class AndroidStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class DocumentMetadata:
    filename: str
    size: int | None


@dataclass(frozen=True)
class StagedDocument:
    path: Path
    staging_dir: Path
    filename: str
    size: int


@dataclass(frozen=True)
class StagedSelection:
    documents: tuple[StagedDocument, ...]

    def __post_init__(self) -> None:
        if not self.documents:
            raise ValueError("La selezione staged non può essere vuota.")
        if len(self.documents) > MAX_PAYLOAD_ROOTS:
            raise ValueError("La selezione staged contiene troppi file.")

    @property
    def root_paths(self) -> tuple[Path, ...]:
        return tuple(document.path for document in self.documents)

    @property
    def filenames(self) -> tuple[str, ...]:
        return tuple(document.filename for document in self.documents)

    @property
    def total_size(self) -> int:
        return sum(document.size for document in self.documents)

    @property
    def count(self) -> int:
        return len(self.documents)


def android_content_resolver() -> Any:
    try:
        from moontransfer_android.android_runtime import (
            AndroidRuntimeError,
            android_context,
        )
    except ImportError as error:
        raise AndroidStorageError("Runtime Android non disponibile.") from error

    try:
        return android_context().getContentResolver()
    except AndroidRuntimeError as error:
        raise AndroidStorageError(str(error)) from error


def query_document_metadata(resolver: Any, uri: Any) -> DocumentMetadata:
    cursor = None
    try:
        cursor = resolver.query(uri, None, None, None, None)
        if cursor is None or not cursor.moveToFirst():
            raise AndroidStorageError(
                "Il provider non ha restituito informazioni sul file."
            )

        name_index = cursor.getColumnIndex(DISPLAY_NAME_COLUMN)
        if name_index < 0 or cursor.isNull(name_index):
            raise AndroidStorageError("Il file selezionato non ha un nome.")
        filename = validate_filename(str(cursor.getString(name_index)))

        size: int | None = None
        size_index = cursor.getColumnIndex(SIZE_COLUMN)
        if size_index >= 0 and not cursor.isNull(size_index):
            reported_size = int(cursor.getLong(size_index))
            if reported_size >= 0:
                size = reported_size
        return DocumentMetadata(filename=filename, size=size)
    except AndroidStorageError:
        raise
    except Exception as error:
        raise AndroidStorageError(
            f"Impossibile leggere le informazioni del file: {error}"
        ) from error
    finally:
        if cursor is not None:
            cursor.close()


def stage_document_uri(
    uri: Any,
    staging_parent: Path,
    *,
    resolver: Any | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> StagedDocument:
    content_resolver = resolver or android_content_resolver()
    metadata = query_document_metadata(content_resolver, uri)
    return _stage_document_with_metadata(
        uri,
        metadata,
        staging_parent,
        resolver=content_resolver,
        cancel_requested=cancel_requested,
        on_progress=on_progress,
    )


def stage_document_uris(
    uris: Iterable[Any],
    staging_parent: Path,
    *,
    resolver: Any | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> StagedSelection:
    selected_uris = tuple(uris)
    if not selected_uris:
        raise AndroidStorageError("Nessun file selezionato.")
    if len(selected_uris) > MAX_PAYLOAD_ROOTS:
        raise AndroidStorageError(
            f"Puoi selezionare al massimo {MAX_PAYLOAD_ROOTS} file."
        )

    content_resolver = resolver or android_content_resolver()
    metadata = tuple(
        query_document_metadata(content_resolver, uri)
        for uri in selected_uris
    )
    name_keys = tuple(portable_name_key(item.filename) for item in metadata)
    if len(set(name_keys)) != len(name_keys):
        raise AndroidStorageError(
            "La selezione contiene nomi file incompatibili o duplicati."
        )

    reported_total = (
        sum(item.size for item in metadata if item.size is not None)
        if all(item.size is not None for item in metadata)
        else None
    )
    completed = 0
    documents: list[StagedDocument] = []
    try:
        for uri, item in zip(selected_uris, metadata, strict=True):
            document = _stage_document_with_metadata(
                uri,
                item,
                staging_parent,
                resolver=content_resolver,
                cancel_requested=cancel_requested,
                on_progress=(
                    None
                    if on_progress is None
                    else lambda copied, _total, base=completed: on_progress(
                        base + copied,
                        reported_total,
                    )
                ),
            )
            documents.append(document)
            completed += document.size
        return StagedSelection(tuple(documents))
    except BaseException:
        for document in documents:
            cleanup_staged_document(document)
        raise


def _stage_document_with_metadata(
    uri: Any,
    metadata: DocumentMetadata,
    staging_parent: Path,
    *,
    resolver: Any,
    cancel_requested: Callable[[], bool] | None,
    on_progress: Callable[[int, int | None], None] | None,
) -> StagedDocument:
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix="document-", dir=staging_parent)
    )
    destination = staging_dir / metadata.filename
    parcel_descriptor = None
    detached_fd: int | None = None
    output_fd: int | None = None

    try:
        if cancel_requested and cancel_requested():
            raise OperationCancelled

        parcel_descriptor = resolver.openFileDescriptor(uri, "r")
        if parcel_descriptor is None:
            raise AndroidStorageError("Il file selezionato non può essere aperto.")
        detached_fd = int(parcel_descriptor.detachFd())
        parcel_descriptor.close()
        parcel_descriptor = None

        output_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        output_flags |= getattr(os, "O_CLOEXEC", 0)
        output_fd = os.open(destination, output_flags, 0o600)
        copied = 0
        with ExitStack() as stack:
            source = stack.enter_context(
                os.fdopen(detached_fd, "rb", closefd=True)
            )
            detached_fd = None
            target = stack.enter_context(
                os.fdopen(output_fd, "wb", closefd=True)
            )
            output_fd = None
            while True:
                if cancel_requested and cancel_requested():
                    raise OperationCancelled
                chunk = source.read(COPY_CHUNK_BYTES)
                if not chunk:
                    break
                target.write(chunk)
                copied += len(chunk)
                if on_progress:
                    on_progress(copied, metadata.size)

        if cancel_requested and cancel_requested():
            raise OperationCancelled
        if metadata.size is not None and copied != metadata.size:
            raise AndroidStorageError(
                "Il file è cambiato durante la copia nell'area privata."
            )

        actual_size = destination.stat().st_size
        if actual_size != copied:
            raise AndroidStorageError("La copia privata del file non è completa.")
        return StagedDocument(
            path=destination,
            staging_dir=staging_dir,
            filename=metadata.filename,
            size=actual_size,
        )
    except BaseException:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    finally:
        if detached_fd is not None:
            os.close(detached_fd)
        if output_fd is not None:
            os.close(output_fd)
        if parcel_descriptor is not None:
            parcel_descriptor.close()


def cleanup_staged_document(document: StagedDocument | None) -> None:
    if document is not None:
        shutil.rmtree(document.staging_dir, ignore_errors=True)


def cleanup_staged_selection(selection: StagedSelection | None) -> None:
    if selection is None:
        return
    for staging_dir in {document.staging_dir for document in selection.documents}:
        shutil.rmtree(staging_dir, ignore_errors=True)


def cleanup_staging_parent(staging_parent: Path) -> None:
    if not staging_parent.is_dir():
        return
    for child in staging_parent.iterdir():
        try:
            if child.is_symlink() or not child.is_dir():
                child.unlink(missing_ok=True)
            else:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            continue


def save_file_to_uri(
    source: Path,
    uri: Any,
    *,
    resolver: Any | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    content_resolver = resolver or android_content_resolver()
    parcel_descriptor = None
    detached_fd: int | None = None

    try:
        source_stat = source.lstat()
        if is_link_or_reparse(source_stat) or not source.is_file():
            raise AndroidStorageError(
                "Il contenuto verificato non è un file regolare."
            )
        if cancel_requested and cancel_requested():
            raise OperationCancelled

        try:
            parcel_descriptor = content_resolver.openFileDescriptor(uri, "rwt")
        except Exception:
            parcel_descriptor = None
        if parcel_descriptor is None:
            parcel_descriptor = content_resolver.openFileDescriptor(uri, "wt")
        if parcel_descriptor is None:
            raise AndroidStorageError(
                "La destinazione selezionata non può essere aperta."
            )
        detached_fd = int(parcel_descriptor.detachFd())
        parcel_descriptor.close()
        parcel_descriptor = None

        copied = 0
        with ExitStack() as stack:
            input_file = stack.enter_context(source.open("rb"))
            initial = os.fstat(input_file.fileno())
            output_file = stack.enter_context(
                os.fdopen(detached_fd, "wb", closefd=True)
            )
            detached_fd = None
            while True:
                if cancel_requested and cancel_requested():
                    raise OperationCancelled
                chunk = input_file.read(COPY_CHUNK_BYTES)
                if not chunk:
                    break
                output_file.write(chunk)
                copied += len(chunk)
                if on_progress:
                    on_progress(copied, initial.st_size)

            output_file.flush()
            try:
                os.fsync(output_file.fileno())
            except OSError as error:
                if error.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EROFS}:
                    raise
            final = os.fstat(input_file.fileno())

        current = source.lstat()
        expected_identity = (
            initial.st_dev,
            initial.st_ino,
            initial.st_size,
            initial.st_mtime_ns,
        )
        if (
            expected_identity
            != (
                final.st_dev,
                final.st_ino,
                final.st_size,
                final.st_mtime_ns,
            )
            or expected_identity
            != (
                current.st_dev,
                current.st_ino,
                current.st_size,
                current.st_mtime_ns,
            )
            or is_link_or_reparse(current)
        ):
            raise AndroidStorageError(
                "Il file verificato è cambiato durante il salvataggio."
            )
        if copied != initial.st_size:
            raise AndroidStorageError("Il salvataggio del file non è completo.")
        if cancel_requested and cancel_requested():
            raise OperationCancelled
        return copied
    except (AndroidStorageError, OperationCancelled):
        raise
    except Exception as error:
        raise AndroidStorageError(
            f"Impossibile salvare il file nella destinazione scelta: {error}"
        ) from error
    finally:
        if detached_fd is not None:
            os.close(detached_fd)
        if parcel_descriptor is not None:
            parcel_descriptor.close()


def save_files_to_tree(
    sources: Iterable[Path],
    tree_uri: Any,
    *,
    container_name: str = "MoonTransfer",
    resolver: Any | None = None,
    documents_contract: Any | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    source_paths = tuple(sources)
    if not source_paths:
        raise AndroidStorageError("Nessun file verificato da salvare.")
    if len(source_paths) > MAX_PAYLOAD_ROOTS:
        raise AndroidStorageError("Troppi file verificati da salvare.")

    portable_container = validate_filename(container_name)
    names = tuple(validate_filename(source.name) for source in source_paths)
    name_keys = tuple(portable_name_key(name) for name in names)
    if len(set(name_keys)) != len(name_keys):
        raise AndroidStorageError(
            "I file verificati hanno nomi incompatibili o duplicati."
        )

    total_size = 0
    for source in source_paths:
        try:
            source_stat = source.lstat()
        except OSError as error:
            raise AndroidStorageError(
                f"File verificato non disponibile: {source.name}."
            ) from error
        if is_link_or_reparse(source_stat) or not source.is_file():
            raise AndroidStorageError(
                "Il contenuto verificato non è composto da file regolari."
            )
        total_size += source_stat.st_size

    content_resolver = resolver or android_content_resolver()
    contract = documents_contract or android_documents_contract()
    container_uri = None
    try:
        if cancel_requested and cancel_requested():
            raise OperationCancelled
        tree_id = contract.getTreeDocumentId(tree_uri)
        root_uri = contract.buildDocumentUriUsingTree(tree_uri, tree_id)
        container_uri = contract.createDocument(
            content_resolver,
            root_uri,
            DIRECTORY_MIME_TYPE,
            portable_container,
        )
        if container_uri is None:
            raise AndroidStorageError(
                "Il provider non ha creato la cartella di destinazione."
            )

        copied_total = 0
        for source, filename in zip(source_paths, names, strict=True):
            if cancel_requested and cancel_requested():
                raise OperationCancelled
            mime_type = mimetypes.guess_type(filename)[0]
            destination_uri = contract.createDocument(
                content_resolver,
                container_uri,
                mime_type or "application/octet-stream",
                filename,
            )
            if destination_uri is None:
                raise AndroidStorageError(
                    f"Il provider non ha creato il file {filename}."
                )
            copied = save_file_to_uri(
                source,
                destination_uri,
                resolver=content_resolver,
                cancel_requested=cancel_requested,
                on_progress=(
                    None
                    if on_progress is None
                    else lambda current, _total, base=copied_total: on_progress(
                        base + current,
                        total_size,
                    )
                ),
            )
            copied_total += copied
            if on_progress:
                on_progress(copied_total, total_size)
        return copied_total
    except (AndroidStorageError, OperationCancelled):
        _delete_document_quietly(contract, content_resolver, container_uri)
        raise
    except Exception as error:
        _delete_document_quietly(contract, content_resolver, container_uri)
        raise AndroidStorageError(
            f"Impossibile salvare i file nella cartella scelta: {error}"
        ) from error


def android_documents_contract() -> Any:
    try:
        from jnius import autoclass
    except ImportError as error:
        raise AndroidStorageError("Runtime Android non disponibile.") from error
    return autoclass("android.provider.DocumentsContract")


def _delete_document_quietly(
    contract: Any,
    resolver: Any,
    uri: Any,
) -> None:
    if uri is None:
        return
    try:
        contract.deleteDocument(resolver, uri)
    except Exception:
        pass


def selected_document_uris(intent: Any) -> tuple[Any, ...]:
    clip_data = intent.getClipData()
    if clip_data is None:
        uri = intent.getData()
        if uri is None:
            raise AndroidStorageError(
                "Android non ha restituito il file selezionato."
            )
        return (uri,)

    item_count = int(clip_data.getItemCount())
    if item_count <= 0:
        raise AndroidStorageError("Android ha restituito una selezione vuota.")
    if item_count > MAX_PAYLOAD_ROOTS:
        raise AndroidStorageError(
            f"Puoi selezionare al massimo {MAX_PAYLOAD_ROOTS} file."
        )

    uris: list[Any] = []
    identities: set[str] = set()
    for index in range(item_count):
        uri = clip_data.getItemAt(index).getUri()
        if uri is None:
            raise AndroidStorageError(
                "Android ha restituito un elemento selezionato non valido."
            )
        identity = str(uri.toString())
        if identity not in identities:
            identities.add(identity)
            uris.append(uri)
    if not uris:
        raise AndroidStorageError("Android ha restituito una selezione vuota.")
    return tuple(uris)


class AndroidFilePicker:
    def __init__(self) -> None:
        try:
            from android import activity as activity_api
            from jnius import autoclass
        except ImportError as error:
            raise AndroidStorageError("Runtime Android non disponibile.") from error

        self._activity_api = activity_api
        self._activity = autoclass(
            "org.kivy.android.PythonActivity"
        ).mActivity
        self._intent_class = autoclass("android.content.Intent")
        self._activity_class = autoclass("android.app.Activity")
        self._on_selected: Callable[[tuple[Any, ...]], None] | None = None
        self._on_cancelled: Callable[[], None] | None = None
        self._on_error: Callable[[Exception], None] | None = None
        self._activity_api.bind(on_activity_result=self._on_activity_result)

    @property
    def pending(self) -> bool:
        return self._on_selected is not None

    def open(
        self,
        *,
        on_selected: Callable[[tuple[Any, ...]], None],
        on_cancelled: Callable[[], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        if self.pending:
            raise AndroidStorageError("La selezione di un file è già in corso.")
        if self._activity is None:
            raise AndroidStorageError("Activity Android non disponibile.")

        self._on_selected = on_selected
        self._on_cancelled = on_cancelled
        self._on_error = on_error
        try:
            intent = self._intent_class(self._intent_class.ACTION_OPEN_DOCUMENT)
            intent.addCategory(self._intent_class.CATEGORY_OPENABLE)
            intent.setType("*/*")
            intent.putExtra(self._intent_class.EXTRA_ALLOW_MULTIPLE, True)
            intent.addFlags(self._intent_class.FLAG_GRANT_READ_URI_PERMISSION)
            self._activity.startActivityForResult(intent, PICK_FILE_REQUEST_CODE)
        except Exception:
            self._clear_callbacks()
            raise

    def close(self) -> None:
        self._clear_callbacks()
        self._activity_api.unbind(on_activity_result=self._on_activity_result)

    def _on_activity_result(
        self,
        request_code: int,
        result_code: int,
        intent: Any,
    ) -> None:
        if request_code != PICK_FILE_REQUEST_CODE or not self.pending:
            return

        on_selected = self._on_selected
        on_cancelled = self._on_cancelled
        on_error = self._on_error
        self._clear_callbacks()

        if result_code != self._activity_class.RESULT_OK or intent is None:
            if on_cancelled:
                on_cancelled()
            return

        try:
            if on_selected:
                on_selected(selected_document_uris(intent))
        except Exception as error:
            if on_error:
                on_error(error)

    def _clear_callbacks(self) -> None:
        self._on_selected = None
        self._on_cancelled = None
        self._on_error = None


class AndroidSavePicker:
    def __init__(self) -> None:
        try:
            from android import activity as activity_api
            from jnius import autoclass
        except ImportError as error:
            raise AndroidStorageError("Runtime Android non disponibile.") from error

        self._activity_api = activity_api
        self._activity = autoclass(
            "org.kivy.android.PythonActivity"
        ).mActivity
        self._intent_class = autoclass("android.content.Intent")
        self._activity_class = autoclass("android.app.Activity")
        self._on_selected: Callable[[Any], None] | None = None
        self._on_cancelled: Callable[[], None] | None = None
        self._on_error: Callable[[Exception], None] | None = None
        self._request_code: int | None = None
        self._activity_api.bind(on_activity_result=self._on_activity_result)

    @property
    def pending(self) -> bool:
        return self._on_selected is not None

    def open(
        self,
        filename: str | None,
        *,
        select_directory: bool = False,
        on_selected: Callable[[Any], None],
        on_cancelled: Callable[[], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        if self.pending:
            raise AndroidStorageError("La scelta della destinazione è già in corso.")
        if self._activity is None:
            raise AndroidStorageError("Activity Android non disponibile.")

        portable_filename = (
            None if select_directory else validate_filename(filename or "")
        )
        mime_type = (
            None
            if portable_filename is None
            else mimetypes.guess_type(portable_filename)[0]
        )
        self._on_selected = on_selected
        self._on_cancelled = on_cancelled
        self._on_error = on_error
        self._request_code = (
            SAVE_DIRECTORY_REQUEST_CODE
            if select_directory
            else SAVE_FILE_REQUEST_CODE
        )
        try:
            action = (
                self._intent_class.ACTION_OPEN_DOCUMENT_TREE
                if select_directory
                else self._intent_class.ACTION_CREATE_DOCUMENT
            )
            intent = self._intent_class(action)
            if not select_directory:
                intent.addCategory(self._intent_class.CATEGORY_OPENABLE)
                intent.setType(mime_type or "application/octet-stream")
                intent.putExtra(
                    self._intent_class.EXTRA_TITLE,
                    portable_filename,
                )
            intent.addFlags(
                self._intent_class.FLAG_GRANT_READ_URI_PERMISSION
                | self._intent_class.FLAG_GRANT_WRITE_URI_PERMISSION
            )
            self._activity.startActivityForResult(intent, self._request_code)
        except Exception:
            self._clear_callbacks()
            raise

    def close(self) -> None:
        self._clear_callbacks()
        self._activity_api.unbind(on_activity_result=self._on_activity_result)

    def _on_activity_result(
        self,
        request_code: int,
        result_code: int,
        intent: Any,
    ) -> None:
        if request_code != self._request_code or not self.pending:
            return

        on_selected = self._on_selected
        on_cancelled = self._on_cancelled
        on_error = self._on_error
        self._clear_callbacks()

        if result_code != self._activity_class.RESULT_OK or intent is None:
            if on_cancelled:
                on_cancelled()
            return

        try:
            uri = intent.getData()
            if uri is None:
                raise AndroidStorageError(
                    "Android non ha restituito la destinazione scelta."
                )
            if on_selected:
                on_selected(uri)
        except Exception as error:
            if on_error:
                on_error(error)

    def _clear_callbacks(self) -> None:
        self._on_selected = None
        self._on_cancelled = None
        self._on_error = None
        self._request_code = None

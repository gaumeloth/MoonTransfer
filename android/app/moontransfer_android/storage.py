from __future__ import annotations

import errno
import mimetypes
import os
import shutil
import tempfile
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moontransfer.cancellation import OperationCancelled
from moontransfer.files import is_link_or_reparse
from moontransfer.protocol import validate_filename


DISPLAY_NAME_COLUMN = "_display_name"
SIZE_COLUMN = "_size"
COPY_CHUNK_BYTES = 1024 * 1024
PICK_FILE_REQUEST_CODE = 0x4D54
SAVE_FILE_REQUEST_CODE = 0x4D55


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

        parcel_descriptor = content_resolver.openFileDescriptor(uri, "r")
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
        self._on_selected: Callable[[Any], None] | None = None
        self._on_cancelled: Callable[[], None] | None = None
        self._on_error: Callable[[Exception], None] | None = None
        self._activity_api.bind(on_activity_result=self._on_activity_result)

    @property
    def pending(self) -> bool:
        return self._on_selected is not None

    def open(
        self,
        *,
        on_selected: Callable[[Any], None],
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
            uri = intent.getData()
            if uri is None:
                raise AndroidStorageError(
                    "Android non ha restituito il file selezionato."
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
        self._activity_api.bind(on_activity_result=self._on_activity_result)

    @property
    def pending(self) -> bool:
        return self._on_selected is not None

    def open(
        self,
        filename: str,
        *,
        on_selected: Callable[[Any], None],
        on_cancelled: Callable[[], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        if self.pending:
            raise AndroidStorageError("La scelta della destinazione è già in corso.")
        if self._activity is None:
            raise AndroidStorageError("Activity Android non disponibile.")

        portable_filename = validate_filename(filename)
        mime_type = mimetypes.guess_type(portable_filename)[0]
        self._on_selected = on_selected
        self._on_cancelled = on_cancelled
        self._on_error = on_error
        try:
            intent = self._intent_class(self._intent_class.ACTION_CREATE_DOCUMENT)
            intent.addCategory(self._intent_class.CATEGORY_OPENABLE)
            intent.setType(mime_type or "application/octet-stream")
            intent.putExtra(self._intent_class.EXTRA_TITLE, portable_filename)
            intent.addFlags(
                self._intent_class.FLAG_GRANT_READ_URI_PERMISSION
                | self._intent_class.FLAG_GRANT_WRITE_URI_PERMISSION
            )
            self._activity.startActivityForResult(intent, SAVE_FILE_REQUEST_CODE)
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
        if request_code != SAVE_FILE_REQUEST_CODE or not self.pending:
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

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANDROID_APP = ROOT / "android" / "app"
sys.path.insert(0, str(ANDROID_APP))

from moontransfer.cancellation import OperationCancelled  # noqa: E402
from moontransfer_android import storage  # noqa: E402


class _Cursor:
    def __init__(self, *, filename: str, size: int | None) -> None:
        self.values = {
            storage.DISPLAY_NAME_COLUMN: filename,
            storage.SIZE_COLUMN: size,
        }
        self.columns = tuple(self.values)
        self.closed = False

    def moveToFirst(self) -> bool:
        return True

    def getColumnIndex(self, name: str) -> int:
        try:
            return self.columns.index(name)
        except ValueError:
            return -1

    def isNull(self, index: int) -> bool:
        return self.values[self.columns[index]] is None

    def getString(self, index: int) -> str:
        return str(self.values[self.columns[index]])

    def getLong(self, index: int) -> int:
        return int(self.values[self.columns[index]])

    def close(self) -> None:
        self.closed = True


class _ParcelDescriptor:
    def __init__(self, source: Path) -> None:
        self.fd = os.open(source, os.O_RDONLY)
        self.closed = False

    def detachFd(self) -> int:
        fd = self.fd
        self.fd = -1
        return fd

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
        self.closed = True


class _WritableParcelDescriptor:
    def __init__(self, destination: Path) -> None:
        self.fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        self.closed = False

    def detachFd(self) -> int:
        fd = self.fd
        self.fd = -1
        return fd

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
        self.closed = True


class _Resolver:
    def __init__(
        self,
        source: Path,
        *,
        filename: str | None = None,
        reported_size: int | None = None,
    ) -> None:
        self.source = source
        self.filename = filename or source.name
        self.reported_size = (
            source.stat().st_size if reported_size is None else reported_size
        )
        self.cursor: _Cursor | None = None

    def query(self, *_args: object) -> _Cursor:
        self.cursor = _Cursor(
            filename=self.filename,
            size=self.reported_size,
        )
        return self.cursor

    def openFileDescriptor(self, *_args: object) -> _ParcelDescriptor:
        return _ParcelDescriptor(self.source)


class _MultiResolver:
    def __init__(self, sources: dict[object, tuple[Path, str]]) -> None:
        self.sources = sources

    def query(self, uri: object, *_args: object) -> _Cursor:
        source, filename = self.sources[uri]
        return _Cursor(filename=filename, size=source.stat().st_size)

    def openFileDescriptor(
        self,
        uri: object,
        _mode: str,
    ) -> _ParcelDescriptor:
        source, _filename = self.sources[uri]
        return _ParcelDescriptor(source)


class _WritableResolver:
    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.mode: str | None = None

    def openFileDescriptor(
        self,
        _uri: object,
        mode: str,
    ) -> _WritableParcelDescriptor:
        self.mode = mode
        return _WritableParcelDescriptor(self.destination)


class _TreeResolver:
    def __init__(self) -> None:
        self.destinations: dict[object, Path] = {}

    def openFileDescriptor(
        self,
        uri: object,
        _mode: str,
    ) -> _WritableParcelDescriptor:
        return _WritableParcelDescriptor(self.destinations[uri])


class _DocumentsContract:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.locations: dict[object, Path] = {"root-uri": root}
        self.deleted: list[object] = []

    def getTreeDocumentId(self, _uri: object) -> str:
        return "root"

    def buildDocumentUriUsingTree(
        self,
        _uri: object,
        _document_id: str,
    ) -> str:
        return "root-uri"

    def createDocument(
        self,
        resolver: _TreeResolver,
        parent_uri: object,
        mime_type: str,
        name: str,
    ) -> str:
        path = self.locations[parent_uri] / name
        uri = f"uri-{len(self.locations)}"
        if mime_type == storage.DIRECTORY_MIME_TYPE:
            path.mkdir()
            self.locations[uri] = path
        else:
            resolver.destinations[uri] = path
        return uri

    def deleteDocument(
        self,
        _resolver: _TreeResolver,
        uri: object,
    ) -> None:
        self.deleted.append(uri)
        path = self.locations[uri]
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


class _Uri:
    def __init__(self, value: str) -> None:
        self.value = value

    def toString(self) -> str:
        return self.value


class _ClipItem:
    def __init__(self, uri: object | None) -> None:
        self.uri = uri

    def getUri(self) -> object | None:
        return self.uri


class _ClipData:
    def __init__(self, uris: tuple[object | None, ...]) -> None:
        self.uris = uris

    def getItemCount(self) -> int:
        return len(self.uris)

    def getItemAt(self, index: int) -> _ClipItem:
        return _ClipItem(self.uris[index])


class _Intent:
    def __init__(
        self,
        *,
        data: object | None = None,
        clip_data: _ClipData | None = None,
    ) -> None:
        self.data = data
        self.clip_data = clip_data

    def getData(self) -> object | None:
        return self.data

    def getClipData(self) -> _ClipData | None:
        return self.clip_data


class _PickerIntent:
    ACTION_OPEN_DOCUMENT = "open-document"
    ACTION_CREATE_DOCUMENT = "create-document"
    ACTION_OPEN_DOCUMENT_TREE = "open-document-tree"
    CATEGORY_OPENABLE = "openable"
    EXTRA_ALLOW_MULTIPLE = "allow-multiple"
    EXTRA_TITLE = "title"
    FLAG_GRANT_READ_URI_PERMISSION = 1
    FLAG_GRANT_WRITE_URI_PERMISSION = 2

    def __init__(self, action: str) -> None:
        self.action = action
        self.categories: list[str] = []
        self.mime_type: str | None = None
        self.extras: dict[str, object] = {}
        self.flags = 0

    def addCategory(self, category: str) -> None:
        self.categories.append(category)

    def setType(self, mime_type: str) -> None:
        self.mime_type = mime_type

    def putExtra(self, name: str, value: object) -> None:
        self.extras[name] = value

    def addFlags(self, flags: int) -> None:
        self.flags |= flags


class _PickerActivity:
    def __init__(self) -> None:
        self.calls: list[tuple[_PickerIntent, int]] = []

    def startActivityForResult(
        self,
        intent: _PickerIntent,
        request_code: int,
    ) -> None:
        self.calls.append((intent, request_code))


class _ActivityClass:
    RESULT_OK = 1


class AndroidStorageTests(unittest.TestCase):
    def test_stage_document_copies_content_into_private_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.bin"
            source.write_bytes(b"payload" * 1000)
            progress: list[tuple[int, int | None]] = []

            document = storage.stage_document_uri(
                object(),
                root / "staging",
                resolver=_Resolver(source, filename="portable.bin"),
                on_progress=lambda copied, total: progress.append((copied, total)),
            )

            self.assertEqual(document.filename, "portable.bin")
            self.assertEqual(document.size, source.stat().st_size)
            self.assertEqual(document.path.read_bytes(), source.read_bytes())
            self.assertEqual(progress[-1], (document.size, document.size))
            self.assertNotEqual(document.path.parent, source.parent)

            storage.cleanup_staged_document(document)
            self.assertFalse(document.staging_dir.exists())

    def test_stage_documents_preserves_selection_and_aggregates_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_source = root / "first-source.bin"
            second_source = root / "second-source.bin"
            first_source.write_bytes(b"first")
            second_source.write_bytes(b"second-payload")
            first_uri = object()
            second_uri = object()
            progress: list[tuple[int, int | None]] = []

            selection = storage.stage_document_uris(
                (first_uri, second_uri),
                root / "staging",
                resolver=_MultiResolver(
                    {
                        first_uri: (first_source, "first.bin"),
                        second_uri: (second_source, "second.bin"),
                    }
                ),
                on_progress=lambda copied, total: progress.append(
                    (copied, total)
                ),
            )

            self.assertEqual(selection.filenames, ("first.bin", "second.bin"))
            self.assertEqual(selection.count, 2)
            self.assertEqual(
                selection.total_size,
                first_source.stat().st_size + second_source.stat().st_size,
            )
            self.assertEqual(selection.root_paths[0].read_bytes(), b"first")
            self.assertEqual(
                selection.root_paths[1].read_bytes(),
                b"second-payload",
            )
            self.assertEqual(
                progress[-1],
                (selection.total_size, selection.total_size),
            )

            staging_dirs = {
                document.staging_dir for document in selection.documents
            }
            storage.cleanup_staged_selection(selection)
            self.assertTrue(all(not path.exists() for path in staging_dirs))

    def test_stage_documents_rejects_portable_name_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first"
            second = root / "second"
            first.write_bytes(b"1")
            second.write_bytes(b"2")
            first_uri = object()
            second_uri = object()

            with self.assertRaisesRegex(
                storage.AndroidStorageError,
                "incompatibili o duplicati",
            ):
                storage.stage_document_uris(
                    (first_uri, second_uri),
                    root / "staging",
                    resolver=_MultiResolver(
                        {
                            first_uri: (first, "File.txt"),
                            second_uri: (second, "file.txt"),
                        }
                    ),
                )

            self.assertFalse((root / "staging").exists())

    def test_stage_document_rejects_nonportable_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.bin"
            source.write_bytes(b"payload")

            with self.assertRaisesRegex(
                storage.AndroidStorageError,
                "informazioni del file",
            ):
                storage.stage_document_uri(
                    object(),
                    root / "staging",
                    resolver=_Resolver(source, filename="invalid:name.bin"),
                )

    def test_stage_document_removes_partial_copy_after_size_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.bin"
            source.write_bytes(b"payload")
            staging = root / "staging"

            with self.assertRaisesRegex(
                storage.AndroidStorageError,
                "è cambiato",
            ):
                storage.stage_document_uri(
                    object(),
                    staging,
                    resolver=_Resolver(source, reported_size=100),
                )

            self.assertEqual(tuple(staging.iterdir()), ())

    def test_stage_document_can_be_cancelled_before_opening(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.bin"
            source.write_bytes(b"payload")
            staging = root / "staging"

            with self.assertRaises(OperationCancelled):
                storage.stage_document_uri(
                    object(),
                    staging,
                    resolver=_Resolver(source),
                    cancel_requested=lambda: True,
                )

            self.assertEqual(tuple(staging.iterdir()), ())

    def test_save_file_writes_verified_content_to_saf_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "verified.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"payload" * 1000)
            progress: list[tuple[int, int]] = []
            resolver = _WritableResolver(destination)

            copied = storage.save_file_to_uri(
                source,
                object(),
                resolver=resolver,
                on_progress=lambda current, total: progress.append(
                    (current, total)
                ),
            )

            self.assertEqual(copied, source.stat().st_size)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertEqual(progress[-1], (copied, copied))
            self.assertEqual(resolver.mode, "rwt")

    def test_save_file_can_be_cancelled_before_opening_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "verified.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"payload")

            with self.assertRaises(OperationCancelled):
                storage.save_file_to_uri(
                    source,
                    object(),
                    resolver=_WritableResolver(destination),
                    cancel_requested=lambda: True,
                )

            self.assertFalse(destination.exists())

    def test_save_files_creates_a_dedicated_saf_container(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "source"
            destination_dir = root / "destination"
            source_dir.mkdir()
            destination_dir.mkdir()
            first = source_dir / "first.txt"
            second = source_dir / "second.bin"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            resolver = _TreeResolver()
            contract = _DocumentsContract(destination_dir)
            progress: list[tuple[int, int]] = []

            copied = storage.save_files_to_tree(
                (first, second),
                "content://tree/root",
                resolver=resolver,
                documents_contract=contract,
                on_progress=lambda current, total: progress.append(
                    (current, total)
                ),
            )

            container = destination_dir / "MoonTransfer"
            self.assertEqual(copied, 11)
            self.assertEqual((container / "first.txt").read_bytes(), b"first")
            self.assertEqual((container / "second.bin").read_bytes(), b"second")
            self.assertEqual(progress[-1], (11, 11))
            self.assertEqual(contract.deleted, [])

    def test_save_files_removes_container_when_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.bin"
            destination = root / "destination"
            source.write_bytes(b"payload")
            destination.mkdir()
            resolver = _TreeResolver()
            contract = _DocumentsContract(destination)
            checks = iter((False, True))

            with self.assertRaises(OperationCancelled):
                storage.save_files_to_tree(
                    (source,),
                    "content://tree/root",
                    resolver=resolver,
                    documents_contract=contract,
                    cancel_requested=lambda: next(checks, True),
                )

            self.assertFalse((destination / "MoonTransfer").exists())
            self.assertEqual(len(contract.deleted), 1)

    def test_selected_document_uris_reads_single_and_clip_data_results(self) -> None:
        first = _Uri("content://documents/first")
        second = _Uri("content://documents/second")

        self.assertEqual(
            storage.selected_document_uris(_Intent(data=first)),
            (first,),
        )
        self.assertEqual(
            storage.selected_document_uris(
                _Intent(clip_data=_ClipData((first, second, first)))
            ),
            (first, second),
        )

    def test_selected_document_uris_rejects_invalid_clip_item(self) -> None:
        with self.assertRaisesRegex(
            storage.AndroidStorageError,
            "elemento selezionato non valido",
        ):
            storage.selected_document_uris(
                _Intent(clip_data=_ClipData((None,)))
            )

    def test_file_picker_requests_multiple_openable_documents(self) -> None:
        picker = object.__new__(storage.AndroidFilePicker)
        picker._activity = _PickerActivity()
        picker._intent_class = _PickerIntent
        picker._on_selected = None
        picker._on_cancelled = None
        picker._on_error = None

        picker.open(
            on_selected=lambda _uris: None,
            on_cancelled=lambda: None,
            on_error=lambda _error: None,
        )

        intent, request_code = picker._activity.calls[0]
        self.assertEqual(intent.action, _PickerIntent.ACTION_OPEN_DOCUMENT)
        self.assertEqual(request_code, storage.PICK_FILE_REQUEST_CODE)
        self.assertIn(_PickerIntent.CATEGORY_OPENABLE, intent.categories)
        self.assertEqual(intent.mime_type, "*/*")
        self.assertIs(
            intent.extras[_PickerIntent.EXTRA_ALLOW_MULTIPLE],
            True,
        )

    def test_save_picker_uses_document_tree_only_for_multiple_files(self) -> None:
        picker = object.__new__(storage.AndroidSavePicker)
        picker._activity = _PickerActivity()
        picker._intent_class = _PickerIntent
        picker._activity_class = _ActivityClass
        picker._on_selected = None
        picker._on_cancelled = None
        picker._on_error = None
        picker._request_code = None
        selected: list[object] = []

        picker.open(
            None,
            select_directory=True,
            on_selected=selected.append,
            on_cancelled=lambda: None,
            on_error=lambda _error: None,
        )

        tree_intent, tree_request_code = picker._activity.calls[-1]
        self.assertEqual(
            tree_intent.action,
            _PickerIntent.ACTION_OPEN_DOCUMENT_TREE,
        )
        self.assertEqual(
            tree_request_code,
            storage.SAVE_DIRECTORY_REQUEST_CODE,
        )
        self.assertEqual(tree_intent.categories, [])
        self.assertIsNone(tree_intent.mime_type)
        destination = _Uri("content://documents/tree")
        picker._on_activity_result(
            tree_request_code,
            _ActivityClass.RESULT_OK,
            _Intent(data=destination),
        )
        self.assertEqual(selected, [destination])

        picker.open(
            "example.txt",
            on_selected=lambda _uri: None,
            on_cancelled=lambda: None,
            on_error=lambda _error: None,
        )
        file_intent, file_request_code = picker._activity.calls[-1]
        self.assertEqual(
            file_intent.action,
            _PickerIntent.ACTION_CREATE_DOCUMENT,
        )
        self.assertEqual(file_request_code, storage.SAVE_FILE_REQUEST_CODE)
        self.assertEqual(
            file_intent.extras[_PickerIntent.EXTRA_TITLE],
            "example.txt",
        )


if __name__ == "__main__":
    unittest.main()

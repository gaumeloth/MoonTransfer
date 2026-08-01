from __future__ import annotations

import os
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


if __name__ == "__main__":
    unittest.main()

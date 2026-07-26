from __future__ import annotations

import errno
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from moontransfer.files import (
    DestinationConflict,
    check_destination,
    cleanup_session_paths,
    create_session_paths,
    directory_payload_size,
    ensure_receive_capacity,
    move_verified_file,
    sha256_file,
    unique_destination_path,
    verify_received_file,
)
from moontransfer.protocol import create_proposal


class FileHelperTests(unittest.TestCase):
    def test_sha256_file_hashes_content_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "different-name.txt"
            path.write_bytes(b"same content")

            self.assertEqual(
                sha256_file(path),
                "a636bd7cd42060a4d07fa1bfbcc010eb7794c2ba721e1e3e4c20335a15b66eaf",
            )

    def test_check_destination_detects_identical_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            target = directory / "example.txt"
            target.write_bytes(b"content")
            proposal = create_proposal(
                filename="example.txt",
                size=target.stat().st_size,
                sha256=sha256_file(target),
            )

            check = check_destination(proposal, directory)

            self.assertEqual(check.conflict, DestinationConflict.IDENTICAL)
            self.assertEqual(check.path, target)

    def test_check_destination_detects_different_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            target = directory / "example.txt"
            target.write_bytes(b"local content")
            incoming = directory / "incoming.txt"
            incoming.write_bytes(b"incoming content")
            proposal = create_proposal(
                filename="example.txt",
                size=incoming.stat().st_size,
                sha256=sha256_file(incoming),
            )

            check = check_destination(proposal, directory)

            self.assertEqual(check.conflict, DestinationConflict.DIFFERENT)
            self.assertEqual(check.path, target)

    def test_unique_destination_path_adds_counter_before_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "example.txt").write_text("one", encoding="utf-8")
            (directory / "example (1).txt").write_text("two", encoding="utf-8")

            self.assertEqual(
                unique_destination_path(directory / "example.txt"),
                directory / "example (2).txt",
            )

    def test_verify_received_file_rejects_wrong_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.txt"
            path.write_bytes(b"content")
            proposal = create_proposal(
                filename="example.txt",
                size=path.stat().st_size,
                sha256="a" * 64,
            )

            with self.assertRaises(ValueError):
                verify_received_file(path, proposal)

    def test_verify_received_file_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            target = directory / "target.txt"
            target.write_bytes(b"content")
            link = directory / "example.txt"
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"Symlink non disponibile: {exc}")

            proposal = create_proposal(
                filename=link.name,
                size=target.stat().st_size,
                sha256=sha256_file(target),
            )

            with self.assertRaisesRegex(ValueError, "file regolare"):
                verify_received_file(link, proposal)

    def test_move_verified_file_uses_alternate_name_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory / "source.txt"
            target = directory / "target.txt"
            source.write_text("incoming", encoding="utf-8")
            target.write_text("existing", encoding="utf-8")

            moved = move_verified_file(source, target, overwrite=False)

            self.assertEqual(moved, directory / "target (1).txt")
            self.assertEqual(moved.read_text(encoding="utf-8"), "incoming")
            self.assertEqual(target.read_text(encoding="utf-8"), "existing")

    def test_move_verified_file_falls_back_across_devices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory / "source.txt"
            target = directory / "target.txt"
            source.write_text("incoming", encoding="utf-8")

            original_replace = Path.replace

            def replace_with_cross_device_error(
                path: Path,
                target_path: Path,
            ) -> Path:
                if path == source:
                    raise OSError(errno.EXDEV, "Invalid cross-device link")
                return original_replace(path, target_path)

            with mock.patch.object(Path, "replace", replace_with_cross_device_error):
                moved = move_verified_file(source, target, overwrite=False)

            self.assertEqual(moved, target)
            self.assertEqual(target.read_text(encoding="utf-8"), "incoming")
            self.assertFalse(source.exists())

    def test_create_session_paths_creates_and_cleans_directories(self) -> None:
        paths = create_session_paths()
        try:
            self.assertTrue(paths.root.is_dir())
            self.assertTrue(paths.croc_config.is_dir())
            self.assertTrue(paths.metadata_send.is_dir())
            self.assertTrue(paths.metadata_receive.is_dir())
            self.assertTrue(paths.main_receive.is_dir())
        finally:
            root = paths.root
            cleanup_session_paths(paths)

        self.assertFalse(root.exists())

    def test_main_receive_staging_can_use_destination_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "destination"
            destination.mkdir()
            paths = create_session_paths(main_receive_parent=destination)
            root = paths.root
            main_receive = paths.main_receive

            try:
                self.assertEqual(main_receive.parent, destination)
                self.assertTrue(main_receive.is_dir())
                self.assertNotEqual(main_receive, root / "main-receive")
            finally:
                cleanup_session_paths(paths)

            self.assertFalse(root.exists())
            self.assertFalse(main_receive.exists())

    def test_directory_payload_size_counts_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            nested = directory / "nested"
            nested.mkdir()
            (directory / "one.bin").write_bytes(b"123")
            (nested / "two.bin").write_bytes(b"4567")

            self.assertEqual(directory_payload_size(directory), 7)

    def test_ensure_receive_capacity_keeps_reserve(self) -> None:
        disk_usage = mock.Mock(free=100)
        with mock.patch("moontransfer.files.shutil.disk_usage", return_value=disk_usage):
            with self.assertRaisesRegex(OSError, "Spazio libero insufficiente"):
                ensure_receive_capacity(Path("/tmp"), 80, reserve_bytes=30)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from moontransfer.cancellation import OperationCancelled
from moontransfer.files import DestinationConflict
from moontransfer.payload import (
    check_payload_destination,
    ensure_source_payload_unchanged,
    publish_received_payload,
    scan_source_payload,
    verify_received_payload,
)
from moontransfer.protocol import ProtocolError


class PayloadTests(unittest.TestCase):
    def test_scans_files_nested_directories_and_empty_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            nested = root / "nested"
            empty = root / "empty"
            nested.mkdir(parents=True)
            empty.mkdir()
            (root / "first.txt").write_text("first", encoding="utf-8")
            (nested / "second.txt").write_text("second", encoding="utf-8")

            payload = scan_source_payload((root,))
            proposal = payload.create_proposal()

            self.assertEqual(proposal.roots, ("source",))
            self.assertEqual(proposal.file_count, 2)
            self.assertEqual(proposal.directory_count, 3)
            self.assertEqual(proposal.total_size, 11)
            self.assertEqual(
                {entry.path for entry in proposal.entries},
                {
                    "source",
                    "source/empty",
                    "source/first.txt",
                    "source/nested",
                    "source/nested/second.txt",
                },
            )

    def test_scans_multiple_roots_in_selection_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            second = base / "second.txt"
            first = base / "first.txt"
            second.write_text("2", encoding="utf-8")
            first.write_text("1", encoding="utf-8")

            payload = scan_source_payload((second, first))

            self.assertEqual(payload.roots, ("second.txt", "first.txt"))
            self.assertEqual(
                payload.root_paths,
                (second.resolve(), first.resolve()),
            )

    def test_rejects_overlapping_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "folder"
            root.mkdir()
            child = root / "child.txt"
            child.write_text("content", encoding="utf-8")

            with self.assertRaises(ProtocolError):
                scan_source_payload((root, child))

    def test_rejects_portable_name_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "folder"
            root.mkdir()
            first = root / "Report.txt"
            second = root / "report.txt"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")
            if first.samefile(second):
                self.skipTest("filesystem is case-insensitive")

            with self.assertRaises(ProtocolError):
                scan_source_payload((root,))

    def test_rejects_portable_root_name_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            first = base / "first" / "Report.txt"
            second = base / "second" / "report.txt"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")

            with self.assertRaises(ProtocolError):
                scan_source_payload((first, second))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks not supported")
    def test_rejects_symbolic_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "folder"
            root.mkdir()
            target = Path(tmp) / "target.txt"
            target.write_text("secret", encoding="utf-8")
            (root / "link.txt").symlink_to(target)

            with self.assertRaises(OSError):
                scan_source_payload((root,))

    def test_detects_file_added_after_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "folder"
            root.mkdir()
            (root / "original.txt").write_text("original", encoding="utf-8")
            payload = scan_source_payload((root,))
            (root / "added.txt").write_text("added", encoding="utf-8")

            with self.assertRaises(OSError):
                ensure_source_payload_unchanged(payload)

    def test_detects_file_changed_after_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "file.txt"
            path.write_text("before", encoding="utf-8")
            payload = scan_source_payload((path,))
            path.write_text("after", encoding="utf-8")

            with self.assertRaises(OSError):
                ensure_source_payload_unchanged(payload)

    def test_scan_can_be_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "file.txt"
            path.write_text("content", encoding="utf-8")

            with self.assertRaises(OperationCancelled):
                scan_source_payload((path,), cancel_requested=lambda: True)

    def test_verifies_exact_received_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source"
            source.mkdir()
            (source / "file.txt").write_text("content", encoding="utf-8")
            proposal = scan_source_payload((source,)).create_proposal()

            staging = base / "staging"
            received = staging / "source"
            received.mkdir(parents=True)
            (received / "file.txt").write_text("content", encoding="utf-8")

            verify_received_payload(staging, proposal)

    def test_rejects_unlisted_received_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source"
            source.mkdir()
            (source / "file.txt").write_text("content", encoding="utf-8")
            proposal = scan_source_payload((source,)).create_proposal()

            staging = base / "staging"
            received = staging / "source"
            received.mkdir(parents=True)
            (received / "file.txt").write_text("content", encoding="utf-8")
            (received / "extra.txt").write_text("extra", encoding="utf-8")

            with self.assertRaises(ValueError):
                verify_received_payload(staging, proposal)

    def test_destination_check_detects_identical_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source"
            source.mkdir()
            (source / "file.txt").write_text("content", encoding="utf-8")
            proposal = scan_source_payload((source,)).create_proposal()

            destination = base / "destination"
            existing = destination / "source"
            existing.mkdir(parents=True)
            (existing / "file.txt").write_text("content", encoding="utf-8")

            check = check_payload_destination(proposal, destination)

            self.assertEqual(check.conflict, DestinationConflict.IDENTICAL)
            self.assertEqual(check.path, existing)

    def test_publishes_single_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "original"
            source.mkdir()
            (source / "file.txt").write_text("content", encoding="utf-8")
            proposal = scan_source_payload((source,)).create_proposal()

            staging = base / "staging"
            received = staging / "original"
            received.mkdir(parents=True)
            (received / "file.txt").write_text("content", encoding="utf-8")
            destination = base / "destination" / "original"

            result = publish_received_payload(
                staging,
                proposal,
                destination,
                overwrite=False,
            )

            self.assertEqual(result, destination)
            self.assertEqual(
                (destination / "file.txt").read_text(encoding="utf-8"),
                "content",
            )

    def test_publishes_multiple_roots_in_container(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            first = base / "first.txt"
            folder = base / "folder"
            first.write_text("first", encoding="utf-8")
            folder.mkdir()
            (folder / "second.txt").write_text("second", encoding="utf-8")
            proposal = scan_source_payload((first, folder)).create_proposal()

            staging = base / "staging"
            staging.mkdir()
            (staging / "first.txt").write_text("first", encoding="utf-8")
            received_folder = staging / "folder"
            received_folder.mkdir()
            (received_folder / "second.txt").write_text(
                "second",
                encoding="utf-8",
            )
            target = base / "destination" / "MoonTransfer"

            result = publish_received_payload(
                staging,
                proposal,
                target,
                overwrite=False,
            )

            self.assertEqual(result, target)
            self.assertEqual(
                (target / "folder" / "second.txt").read_text(encoding="utf-8"),
                "second",
            )
            self.assertFalse(staging.exists())


if __name__ == "__main__":
    unittest.main()

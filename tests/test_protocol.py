from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from moontransfer import protocol


class ProtocolTests(unittest.TestCase):
    def test_create_proposal_contains_control_codes(self) -> None:
        proposal = protocol.create_proposal(
            filename="example.txt",
            size=12,
            sha256="a" * 64,
        )

        self.assertEqual(proposal.version, protocol.PROTOCOL_VERSION)
        self.assertEqual(proposal.type, protocol.PROPOSAL_TYPE)
        self.assertEqual(proposal.filename, "example.txt")
        self.assertEqual(proposal.hash_algorithm, protocol.HASH_ALGORITHM)
        self.assertRegex(proposal.main_code, r"^[0-9a-f]{32}$")

    def test_generated_croc_code_has_no_fixed_hyphenated_room_prefix(self) -> None:
        codes = {protocol.generate_croc_code() for _ in range(20)}

        self.assertEqual(len(codes), 20)
        for code in codes:
            self.assertRegex(code, r"^[0-9a-f]{32}$")
            self.assertNotIn("-", code)
            self.assertNotIn("_", code)

    def test_code_id_is_short_and_stable(self) -> None:
        self.assertEqual(protocol.code_id("secret-code"), protocol.code_id("secret-code"))
        self.assertRegex(protocol.code_id("secret-code"), r"^[0-9a-f]{12}$")

    def test_rejects_path_like_filename(self) -> None:
        with self.assertRaises(protocol.ProtocolError):
            protocol.create_proposal(
                filename="../secret.txt",
                size=12,
                sha256="a" * 64,
            )

        with self.assertRaises(protocol.ProtocolError):
            protocol.create_proposal(
                filename=r"folder\secret.txt",
                size=12,
                sha256="a" * 64,
            )

    def test_rejects_nonportable_filename(self) -> None:
        invalid_names = (
            "CON",
            "NUL.txt",
            "COM1.log",
            "COM¹.log",
            "LPT9",
            "CONOUT$",
            "report:alternate.txt",
            "trailing-space ",
            "trailing-dot.",
            "line\nbreak.txt",
            "spoof\u202etxt.exe",
            "x" * 256,
        )

        for filename in invalid_names:
            with self.subTest(filename=filename):
                with self.assertRaises(protocol.ProtocolError):
                    protocol.create_proposal(
                        filename=filename,
                        size=12,
                        sha256="a" * 64,
                    )

    def test_accepts_normal_unicode_filename(self) -> None:
        proposal = protocol.create_proposal(
            filename="vacanza-città.txt",
            size=12,
            sha256="a" * 64,
        )

        self.assertEqual(proposal.filename, "vacanza-città.txt")

    def test_rejects_invalid_hash(self) -> None:
        with self.assertRaises(protocol.ProtocolError):
            protocol.create_proposal(
                filename="example.txt",
                size=12,
                sha256="not-a-sha",
            )

    def test_rejects_invalid_size(self) -> None:
        for size in (-1, True, protocol.MAX_TRANSFER_FILE_BYTES + 1):
            with self.subTest(size=size):
                with self.assertRaises(protocol.ProtocolError):
                    protocol.create_proposal(
                        filename="example.txt",
                        size=size,
                        sha256="a" * 64,
                    )

    def test_read_rejects_invalid_internal_code(self) -> None:
        proposal = protocol.create_proposal(
            filename="example.txt",
            size=12,
            sha256="a" * 64,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.json"
            protocol.write_control_file(path, proposal)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["main_code"] = "not-a-moontransfer-code"
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaises(protocol.ProtocolError):
                protocol.read_proposal(path)

    def test_round_trip_proposal(self) -> None:
        proposal = protocol.create_proposal(
            filename="example.txt",
            size=12,
            sha256="a" * 64,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.json"
            protocol.write_control_file(path, proposal)

            self.assertEqual(protocol.read_proposal(path), proposal)

    def test_round_trip_payload_manifest(self) -> None:
        proposal = protocol.create_payload_proposal(
            roots=("folder", "note.txt"),
            entries=(
                protocol.PayloadEntry(
                    path="folder",
                    type=protocol.ENTRY_DIRECTORY,
                ),
                protocol.PayloadEntry(
                    path="folder/empty",
                    type=protocol.ENTRY_DIRECTORY,
                ),
                protocol.PayloadEntry(
                    path="folder/data.bin",
                    type=protocol.ENTRY_FILE,
                    size=4,
                    sha256="a" * 64,
                ),
                protocol.PayloadEntry(
                    path="note.txt",
                    type=protocol.ENTRY_FILE,
                    size=3,
                    sha256="b" * 64,
                ),
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.json"
            protocol.write_control_file(path, proposal)
            restored = protocol.read_proposal(path)

        self.assertEqual(restored, proposal)
        self.assertEqual(restored.total_size, 7)
        self.assertEqual(restored.file_count, 2)
        self.assertEqual(restored.directory_count, 2)

    def test_reads_legacy_single_file_proposal(self) -> None:
        data = {
            "version": protocol.LEGACY_PROTOCOL_VERSION,
            "type": protocol.PROPOSAL_TYPE,
            "session_id": "a" * 32,
            "filename": "legacy.txt",
            "size": 6,
            "hash_algorithm": protocol.HASH_ALGORITHM,
            "sha256": "b" * 64,
            "main_code": "c" * 32,
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            proposal = protocol.read_proposal(path)

        self.assertEqual(proposal.version, protocol.LEGACY_PROTOCOL_VERSION)
        self.assertTrue(proposal.is_single_file)
        self.assertEqual(proposal.filename, "legacy.txt")
        self.assertEqual(proposal.sha256, "b" * 64)

    def test_rejects_payload_path_traversal(self) -> None:
        with self.assertRaises(protocol.ProtocolError):
            protocol.create_payload_proposal(
                roots=("folder",),
                entries=(
                    protocol.PayloadEntry(
                        path="folder",
                        type=protocol.ENTRY_DIRECTORY,
                    ),
                    protocol.PayloadEntry(
                        path="folder/../secret.txt",
                        type=protocol.ENTRY_FILE,
                        size=1,
                        sha256="a" * 64,
                    ),
                ),
            )

    def test_rejects_case_insensitive_payload_collision(self) -> None:
        with self.assertRaises(protocol.ProtocolError):
            protocol.create_payload_proposal(
                roots=("folder",),
                entries=(
                    protocol.PayloadEntry(
                        path="folder",
                        type=protocol.ENTRY_DIRECTORY,
                    ),
                    protocol.PayloadEntry(
                        path="folder/File.txt",
                        type=protocol.ENTRY_FILE,
                        size=1,
                        sha256="a" * 64,
                    ),
                    protocol.PayloadEntry(
                        path="folder/file.txt",
                        type=protocol.ENTRY_FILE,
                        size=1,
                        sha256="b" * 64,
                    ),
                ),
            )

    def test_read_rejects_manifest_totals_that_do_not_match_entries(self) -> None:
        proposal = protocol.create_proposal(
            filename="example.txt",
            size=12,
            sha256="a" * 64,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.json"
            protocol.write_control_file(path, proposal)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["total_size"] = 13
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaises(protocol.ProtocolError):
                protocol.read_proposal(path)

if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

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
        self.assertRegex(proposal.decision_code, r"^[0-9a-f]{32}$")
        self.assertNotEqual(proposal.main_code, proposal.decision_code)

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

    def test_rejects_invalid_hash(self) -> None:
        with self.assertRaises(protocol.ProtocolError):
            protocol.create_proposal(
                filename="example.txt",
                size=12,
                sha256="not-a-sha",
            )

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

    def test_round_trip_decision(self) -> None:
        proposal = protocol.create_proposal(
            filename="example.txt",
            size=12,
            sha256="a" * 64,
        )
        decision = protocol.create_decision(
            session_id=proposal.session_id,
            accepted=True,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decision.json"
            protocol.write_control_file(path, decision)

            self.assertEqual(
                protocol.read_decision(
                    path,
                    expected_session_id=proposal.session_id,
                ),
                decision,
            )

    def test_rejects_decision_from_other_session(self) -> None:
        decision = protocol.create_decision(
            session_id="expected-session",
            accepted=False,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decision.json"
            protocol.write_control_file(path, decision)

            with self.assertRaises(protocol.ProtocolError):
                protocol.read_decision(
                    path,
                    expected_session_id="other-session",
                )

if __name__ == "__main__":
    unittest.main()

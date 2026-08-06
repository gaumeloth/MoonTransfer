from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from moontransfer.build_info import (
    BUILD_INFO_SCHEMA_VERSION,
    MAX_BUILD_INFO_BYTES,
    load_build_info,
)


class BuildInfoTests(unittest.TestCase):
    def test_loads_valid_embedded_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "build-info.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": BUILD_INFO_SCHEMA_VERSION,
                        "version": "0.1.0-alpha.3",
                        "commit": "a" * 40,
                        "croc_version": "11.0.1",
                        "protocol_version": 2,
                    }
                ),
                encoding="utf-8",
            )

            info = load_build_info(path)

        self.assertTrue(info.embedded)
        self.assertEqual(info.version, "0.1.0-alpha.3")
        self.assertEqual(info.commit, "a" * 40)
        self.assertEqual(info.short_commit, "a" * 12)
        self.assertEqual(info.croc_version, "11.0.1")
        self.assertEqual(info.protocol_version, 2)

    def test_missing_invalid_or_oversized_metadata_uses_source_fallback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = load_build_info(root / "missing.json")

            invalid_path = root / "invalid.json"
            invalid_path.write_text('{"commit": "not-a-commit"}', encoding="utf-8")
            invalid = load_build_info(invalid_path)

            oversized_path = root / "oversized.json"
            oversized_path.write_bytes(b"x" * (MAX_BUILD_INFO_BYTES + 1))
            oversized = load_build_info(oversized_path)

            stale_path = root / "stale.json"
            stale_path.write_text(
                json.dumps(
                    {
                        "schema_version": BUILD_INFO_SCHEMA_VERSION,
                        "version": "0.1.0-alpha.3",
                        "commit": "f" * 40,
                        "croc_version": "11.0.1",
                        "protocol_version": 999,
                    }
                ),
                encoding="utf-8",
            )
            stale = load_build_info(stale_path)

        for info in (missing, invalid, oversized, stale):
            self.assertFalse(info.embedded)
            self.assertTrue(info.version.endswith("-dev"))
            self.assertIsNone(info.commit)
            self.assertIsNone(info.croc_version)

    def test_diagnostics_contains_build_identity_without_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "build-info.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": BUILD_INFO_SCHEMA_VERSION,
                        "version": "0.1.0-dev.0123456789ab",
                        "commit": "0123456789abcdef" * 2 + "01234567",
                        "croc_version": "11.0.1",
                        "protocol_version": 2,
                    }
                ),
                encoding="utf-8",
            )
            diagnostics = load_build_info(path).diagnostics()

        self.assertIn("MoonTransfer: 0.1.0-dev.0123456789ab", diagnostics)
        self.assertIn("croc incorporato: 11.0.1", diagnostics)
        self.assertIn("Protocollo MoonTransfer: 2", diagnostics)
        self.assertNotIn(str(path), diagnostics)
        self.assertNotIn("CROC_SECRET", diagnostics)


if __name__ == "__main__":
    unittest.main()

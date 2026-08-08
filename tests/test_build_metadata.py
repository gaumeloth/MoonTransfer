from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import build_metadata


PYPROJECT = """\
[project]
name = "moontransfer"
version = "0.1.0"

[tool.moontransfer.croc]
version = "11.0.1"
"""


class BuildMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
        package = self.root / "src" / "moontransfer"
        package.mkdir(parents=True)
        (package / "build_info.py").write_text(
            "BUILD_INFO_SCHEMA_VERSION = 1\n",
            encoding="utf-8",
        )
        (package / "protocol.py").write_text(
            "PROTOCOL_VERSION = 2\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_explicit_release_identity_is_preserved(self) -> None:
        metadata = build_metadata.create_build_metadata(
            self.root,
            version="0.1.0-alpha.3",
            commit="a" * 40,
        )

        self.assertEqual(metadata.version, "0.1.0-alpha.3")
        self.assertEqual(metadata.commit, "a" * 40)
        self.assertEqual(metadata.croc_version, "11.0.1")
        self.assertEqual(metadata.protocol_version, 2)

    def test_development_identity_uses_current_commit(self) -> None:
        commit = "b" * 40
        with mock.patch.object(
            build_metadata,
            "_git_output",
            side_effect=(commit, None),
        ):
            metadata = build_metadata.create_build_metadata(self.root)

        self.assertEqual(metadata.commit, commit)
        self.assertEqual(metadata.version, f"0.1.0-dev.{commit[:12]}")

    def test_exact_release_tag_becomes_build_version(self) -> None:
        commit = "c" * 40
        with (
            mock.patch.object(
                build_metadata,
                "_git_output",
                side_effect=(commit, "v0.1.0-beta.1"),
            ),
            mock.patch.object(
                build_metadata,
                "git_worktree_is_clean",
                return_value=True,
            ),
        ):
            metadata = build_metadata.create_build_metadata(self.root)

        self.assertEqual(metadata.version, "0.1.0-beta.1")

    def test_dirty_tagged_checkout_uses_development_version(self) -> None:
        commit = "c" * 40
        with (
            mock.patch.object(
                build_metadata,
                "_git_output",
                side_effect=(commit, "v0.1.0-alpha.3"),
            ),
            mock.patch.object(
                build_metadata,
                "git_worktree_is_clean",
                return_value=False,
            ),
        ):
            metadata = build_metadata.create_build_metadata(self.root)

        self.assertEqual(metadata.version, f"0.1.0-dev.{commit[:12]}")

    def test_writer_produces_stable_valid_json(self) -> None:
        metadata = build_metadata.create_build_metadata(
            self.root,
            version="0.1.0-alpha.3",
            commit="d" * 40,
        )
        path = self.root / "generated" / "build-info.json"

        build_metadata.write_build_metadata(path, metadata)

        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "0.1.0-alpha.3")
        self.assertEqual(data["commit"], "d" * 40)
        self.assertEqual(data["schema_version"], 1)
        self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

    def test_integer_constants_are_read_without_importing_runtime_modules(
        self,
    ) -> None:
        path = self.root / "constants.py"
        path.write_text(
            "PROTOCOL_VERSION = 3\nUNRELATED = 9\n",
            encoding="utf-8",
        )

        self.assertEqual(
            build_metadata.read_integer_constant(path, "PROTOCOL_VERSION"),
            3,
        )
        with self.assertRaisesRegex(RuntimeError, "MISSING"):
            build_metadata.read_integer_constant(path, "MISSING")

    def test_invalid_explicit_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "build.version"):
            build_metadata.create_build_metadata(
                self.root,
                version="../alpha.3",
                commit="e" * 40,
            )

        with self.assertRaisesRegex(ValueError, "versione progetto"):
            build_metadata.create_build_metadata(
                self.root,
                version="9.9.9-alpha.1",
                commit="e" * 40,
            )

        with self.assertRaisesRegex(ValueError, "Commit"):
            build_metadata.create_build_metadata(
                self.root,
                version="0.1.0-alpha.3",
                commit="not-a-commit",
            )

        with self.assertRaisesRegex(ValueError, "Commit"):
            build_metadata.create_build_metadata(
                self.root,
                version="0.1.0-alpha.3",
                commit="",
            )


if __name__ == "__main__":
    unittest.main()

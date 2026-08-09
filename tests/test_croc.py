from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moontransfer import croc


class CrocCommandTests(unittest.TestCase):
    def test_parse_send_code_returns_code(self) -> None:
        self.assertEqual(
            croc.parse_send_code("Code is: alpha-beta-gamma"),
            "alpha-beta-gamma",
        )

    def test_parse_send_code_ignores_unrelated_lines(self) -> None:
        self.assertIsNone(croc.parse_send_code("waiting for receiver"))

    def test_parse_send_code_strips_whitespace(self) -> None:
        self.assertEqual(
            croc.parse_send_code("Code is:   alpha beta   "),
            "alpha beta",
        )

    def test_send_preparation_complete_uses_the_code_announcement(self) -> None:
        self.assertTrue(croc.send_preparation_complete("Code is: <hidden>"))
        self.assertFalse(
            croc.send_preparation_complete("Sending 2 files (4.2 MB)")
        )

    def test_parse_version_output_accepts_legacy_v_prefix(self) -> None:
        self.assertEqual(
            croc.parse_version_output("croc version v10.4.13"),
            "10.4.13",
        )

    def test_parse_version_output_accepts_current_format(self) -> None:
        self.assertEqual(
            croc.parse_version_output("croc version 10.7.0"),
            "10.7.0",
        )

    def test_parse_version_output_rejects_unrelated_versions(self) -> None:
        self.assertIsNone(croc.parse_version_output("Python 3.13.11"))

    def test_build_send_args(self) -> None:
        path = Path("/tmp/example file.txt")

        self.assertEqual(
            croc.build_send_args(path),
            [
                "--classic=false",
                "--ignore-stdin",
                "--disable-clipboard",
                "send",
                "--no-local",
                str(path),
            ],
        )

    def test_build_send_args_accepts_multiple_paths(self) -> None:
        paths = (Path("/tmp/first.txt"), Path("/tmp/folder"))

        self.assertEqual(
            croc.build_send_args(paths),
            [
                "--classic=false",
                "--ignore-stdin",
                "--disable-clipboard",
                "send",
                "--no-local",
                *(str(path) for path in paths),
            ],
        )

    def test_build_send_args_rejects_empty_selection(self) -> None:
        with self.assertRaises(ValueError):
            croc.build_send_args(())

    def test_build_receive_args(self) -> None:
        self.assertEqual(
            croc.build_receive_args(),
            ["--classic=false", "--ignore-stdin", "--yes", "--overwrite"],
        )

    def test_build_prompted_receive_args(self) -> None:
        self.assertEqual(
            croc.build_prompted_receive_args(),
            ["--classic=false", "--overwrite"],
        )

    def test_secret_preview_hides_environment_secret(self) -> None:
        preview = croc.build_secret_preview(
            "/usr/bin/croc",
            croc.build_receive_args(),
        )

        self.assertIn("CROC_SECRET=<hidden>", preview)

    def test_build_process_environment_isolates_config_and_sets_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "croc-config"

            env = croc.build_process_environment(
                config_dir,
                secret="secret-code",
            )

            self.assertEqual(env[croc.CROC_SECRET_ENV], "secret-code")
            self.assertTrue(env["XDG_CONFIG_HOME"].startswith(str(config_dir)))
            self.assertTrue(env["APPDATA"].startswith(str(config_dir)))
            self.assertTrue(env["LOCALAPPDATA"].startswith(str(config_dir)))
            self.assertTrue(env["HOME"].startswith(str(config_dir)))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

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

    def test_build_send_args(self) -> None:
        path = Path("/tmp/example file.txt")

        self.assertEqual(
            croc.build_send_args(path),
            [
                "--ignore-stdin",
                "--disable-clipboard",
                "send",
                "--no-local",
                str(path),
            ],
        )

    def test_build_send_args_with_custom_code(self) -> None:
        path = Path("/tmp/example file.txt")

        self.assertEqual(
            croc.build_send_args(path, code="moon-secret"),
            [
                "--ignore-stdin",
                "--disable-clipboard",
                "send",
                "--no-local",
                "--code",
                "moon-secret",
                str(path),
            ],
        )

    def test_build_receive_args(self) -> None:
        self.assertEqual(
            croc.build_receive_args(),
            ["--ignore-stdin", "--yes", "--overwrite"],
        )

    def test_build_receive_args_with_code(self) -> None:
        self.assertEqual(
            croc.build_receive_args("secret-code"),
            ["--ignore-stdin", "--yes", "--overwrite", "secret-code"],
        )

    def test_build_prompted_receive_args_with_code(self) -> None:
        self.assertEqual(
            croc.build_prompted_receive_args("secret-code"),
            ["--overwrite", "secret-code"],
        )

    def test_hidden_code_receive_preview_hides_positional_code(self) -> None:
        preview = croc.build_hidden_code_receive_preview(
            "/usr/bin/croc",
            croc.build_receive_args("secret-code"),
        )

        self.assertIn("<hidden>", preview)
        self.assertNotIn("secret-code", preview)


if __name__ == "__main__":
    unittest.main()

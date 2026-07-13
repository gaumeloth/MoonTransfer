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

    def test_build_receive_args(self) -> None:
        self.assertEqual(
            croc.build_receive_args(),
            ["--ignore-stdin", "--yes", "--overwrite"],
        )

    def test_build_receive_environment(self) -> None:
        self.assertEqual(
            croc.build_receive_environment("secret-code"),
            {croc.CROC_SECRET_ENV: "secret-code"},
        )

    def test_receive_preview_hides_secret(self) -> None:
        preview = croc.build_receive_preview("/usr/bin/croc", croc.build_receive_args())

        self.assertIn("CROC_SECRET=<hidden>", preview)
        self.assertNotIn("secret-code", preview)


if __name__ == "__main__":
    unittest.main()

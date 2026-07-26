from __future__ import annotations

import unittest

from moontransfer.runner import CrocRunner, redact_sensitive_text, split_process_records


class RunnerTests(unittest.TestCase):
    def test_split_process_records_handles_carriage_returns(self) -> None:
        records, remaining = split_process_records(b"first\rsecond\rpartial")

        self.assertEqual(records, [b"first", b"second"])
        self.assertEqual(remaining, b"partial")

    def test_split_process_records_handles_final_separator(self) -> None:
        records, remaining = split_process_records(b"first\rsecond\n")

        self.assertEqual(records, [b"first", b"second", b""])
        self.assertEqual(remaining, b"")

    def test_redact_sensitive_text_hides_every_secret(self) -> None:
        redacted = redact_sensitive_text(
            "Code is: visible-code\nCROC_SECRET=internal-code",
            ("visible-code", "internal-code"),
        )

        self.assertEqual(
            redacted,
            "Code is: <hidden>\nCROC_SECRET=<hidden>",
        )

    def test_runner_redacts_secret_split_across_chunks(self) -> None:
        displayed: list[str] = []
        runner = CrocRunner(
            "/nonexistent/croc",
            append_text=lambda _text: None,
            append_line=displayed.append,
        )
        runner._sensitive_values = ("secret-code",)

        runner._handle_chunk(b"Code is: secret", "_stdout_buffer")
        self.assertEqual(displayed, [])

        runner._handle_chunk(b"-code\n", "_stdout_buffer")
        self.assertEqual(displayed, ["Code is: <hidden>", ""])


if __name__ == "__main__":
    unittest.main()

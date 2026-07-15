from __future__ import annotations

import unittest

from moontransfer.runner import split_process_records


class RunnerTests(unittest.TestCase):
    def test_split_process_records_handles_carriage_returns(self) -> None:
        records, remaining = split_process_records(b"first\rsecond\rpartial")

        self.assertEqual(records, [b"first", b"second"])
        self.assertEqual(remaining, b"partial")

    def test_split_process_records_handles_final_separator(self) -> None:
        records, remaining = split_process_records(b"first\rsecond\n")

        self.assertEqual(records, [b"first", b"second", b""])
        self.assertEqual(remaining, b"")


if __name__ == "__main__":
    unittest.main()

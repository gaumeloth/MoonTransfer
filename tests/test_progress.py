from __future__ import annotations

import unittest

from moontransfer.progress import (
    format_duration,
    format_file_size,
    format_transfer_rate,
    parse_announced_transfer_total,
    parse_size_value,
    parse_transfer_progress,
)


class ProgressTests(unittest.TestCase):
    def test_format_file_size_bytes(self) -> None:
        self.assertEqual(format_file_size(512), "512 B")

    def test_format_file_size_kib(self) -> None:
        self.assertEqual(format_file_size(1536), "1.5 KiB")

    def test_format_file_size_mib(self) -> None:
        self.assertEqual(format_file_size(2 * 1024 * 1024), "2.0 MiB")

    def test_format_duration_seconds(self) -> None:
        self.assertEqual(format_duration(7), "7s")

    def test_format_duration_minutes(self) -> None:
        self.assertEqual(format_duration(65), "1m 05s")

    def test_format_transfer_rate(self) -> None:
        self.assertEqual(format_transfer_rate(2 * 1024 * 1024), "2.0 MiB/s")

    def test_parse_size_value_decimal_unit(self) -> None:
        self.assertEqual(parse_size_value("21", "MB"), 21_000_000)

    def test_parse_size_value_binary_unit(self) -> None:
        self.assertEqual(parse_size_value("2", "MiB"), 2 * 1024 * 1024)

    def test_parse_announced_send_total(self) -> None:
        self.assertEqual(
            parse_announced_transfer_total(
                "Sending 'moontransfer-progress-source.bin' (20.0 MB)"
            ),
            20_000_000,
        )

    def test_parse_announced_receive_total(self) -> None:
        self.assertEqual(
            parse_announced_transfer_total(
                "Receiving 'moontransfer-progress-source.bin' (20.0 MB)"
            ),
            20_000_000,
        )

    def test_parse_transfer_progress_with_speed(self) -> None:
        sample = parse_transfer_progress(
            "moontran...  65% |████| (14/21 MB, 137 MB/s) [0s:0s]"
        )

        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertEqual(sample.percent, 65)
        self.assertEqual(sample.transferred_bytes, 14_000_000)
        self.assertEqual(sample.total_bytes, 21_000_000)
        self.assertEqual(sample.speed_bps, 137_000_000)

    def test_parse_transfer_progress_without_speed(self) -> None:
        sample = parse_transfer_progress(
            "moontran...   0% | | ( 0 B/21 MB) [0s:0s]"
        )

        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertEqual(sample.percent, 0)
        self.assertEqual(sample.transferred_bytes, 0)
        self.assertEqual(sample.total_bytes, 21_000_000)
        self.assertIsNone(sample.speed_bps)

    def test_parse_hashing_progress_is_not_transfer_progress(self) -> None:
        self.assertIsNone(
            parse_transfer_progress(
                "Hashing moontransfer...  99% |████| (3.9 GB/s) [0s:0s]"
            )
        )


if __name__ == "__main__":
    unittest.main()

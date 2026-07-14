from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtCore import QProcess

from moontransfer.app import (
    croc_status_from_line,
    external_process_environment,
    format_duration,
    format_file_size,
    format_transfer_rate,
    folder_open_command,
    parse_announced_transfer_total,
    parse_size_value,
    parse_transfer_progress,
    process_result_message,
    split_process_records,
)


class ProcessResultMessageTests(unittest.TestCase):
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

    def test_split_process_records_handles_carriage_returns(self) -> None:
        records, remaining = split_process_records(b"first\rsecond\rpartial")

        self.assertEqual(records, [b"first", b"second"])
        self.assertEqual(remaining, b"partial")

    def test_split_process_records_handles_final_separator(self) -> None:
        records, remaining = split_process_records(b"first\rsecond\n")

        self.assertEqual(records, [b"first", b"second", b""])
        self.assertEqual(remaining, b"")

    def test_status_from_code_line(self) -> None:
        self.assertEqual(
            croc_status_from_line("Code is: alpha-beta", role="send"),
            "Codice generato. Comunicalo alla persona che deve ricevere il file.",
        )

    def test_status_from_waiting_line(self) -> None:
        self.assertEqual(
            croc_status_from_line("waiting for receiver", role="send"),
            "In attesa che il destinatario usi il codice.",
        )

    def test_status_from_transfer_line(self) -> None:
        self.assertEqual(
            croc_status_from_line("sending file.txt", role="send"),
            "Trasferimento in corso.",
        )

    def test_status_from_unrelated_line(self) -> None:
        self.assertIsNone(croc_status_from_line("some unrelated output", role="send"))

    def test_linux_folder_open_command_prefers_xdg_open(self) -> None:
        path = "/usr/bin/xdg-open"

        self.assertEqual(
            folder_open_command(
                Path("/tmp"),
                platform_name="linux",
                which=lambda command: path if command == "xdg-open" else None,
            ),
            [path, "/tmp"],
        )

    def test_linux_folder_open_command_falls_back_to_gio(self) -> None:
        self.assertEqual(
            folder_open_command(
                Path("/tmp"),
                platform_name="linux",
                which=lambda command: "/usr/bin/gio" if command == "gio" else None,
            ),
            ["/usr/bin/gio", "open", "/tmp"],
        )

    def test_unknown_folder_open_command_returns_none(self) -> None:
        self.assertIsNone(
            folder_open_command(
                Path("/tmp"),
                platform_name="unknown",
                which=lambda command: None,
            )
        )

    def test_external_process_environment_restores_original_library_path(self) -> None:
        self.assertEqual(
            external_process_environment(
                {
                    "LD_LIBRARY_PATH": "/tmp/app/_internal",
                    "LD_LIBRARY_PATH_ORIG": "/usr/lib",
                },
                frozen=True,
            ),
            {"LD_LIBRARY_PATH": "/usr/lib"},
        )

    def test_external_process_environment_removes_empty_original_library_path(self) -> None:
        self.assertEqual(
            external_process_environment(
                {
                    "LD_LIBRARY_PATH": "/tmp/app/_internal",
                    "LD_LIBRARY_PATH_ORIG": "",
                },
                frozen=True,
            ),
            {},
        )

    def test_external_process_environment_removes_frozen_qt_paths(self) -> None:
        self.assertEqual(
            external_process_environment(
                {
                    "LD_LIBRARY_PATH": "/tmp/app/_internal",
                    "QT_PLUGIN_PATH": "/tmp/app/qt/plugins",
                    "QML2_IMPORT_PATH": "/tmp/app/qml",
                    "QT_QPA_PLATFORM_PLUGIN_PATH": "/tmp/app/platforms",
                    "PATH": "/usr/bin",
                },
                frozen=True,
            ),
            {"PATH": "/usr/bin"},
        )

    def test_external_process_environment_keeps_normal_library_path(self) -> None:
        self.assertEqual(
            external_process_environment(
                {"LD_LIBRARY_PATH": "/custom/lib"},
                frozen=False,
            ),
            {"LD_LIBRARY_PATH": "/custom/lib"},
        )

    def test_success_message(self) -> None:
        self.assertEqual(
            process_result_message(
                action="Invio",
                exit_code=0,
                exit_status=QProcess.ExitStatus.NormalExit,
            ),
            "Invio: completato.",
        )

    def test_error_message(self) -> None:
        self.assertEqual(
            process_result_message(
                action="Ricezione",
                exit_code=1,
                exit_status=QProcess.ExitStatus.NormalExit,
            ),
            "Ricezione: terminato con errore. Controlla l'output tecnico.",
        )

    def test_crash_message(self) -> None:
        self.assertEqual(
            process_result_message(
                action="Invio",
                exit_code=1,
                exit_status=QProcess.ExitStatus.CrashExit,
            ),
            "Invio: interrotto. Controlla l'output tecnico.",
        )


if __name__ == "__main__":
    unittest.main()

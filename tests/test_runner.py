from __future__ import annotations

import os
import sys
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

from moontransfer.runner import CrocRunner, redact_sensitive_text, split_process_records


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

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

    def test_stop_returns_before_process_termination(self) -> None:
        displayed: list[str] = []
        runner = CrocRunner(
            sys.executable,
            append_text=lambda _text: None,
            append_line=lambda text="": displayed.append(text),
        )
        try:
            runner.start(
                ["-c", "import time; time.sleep(60)"],
                preview="python <sleep>",
            )

            before_stop = time.monotonic()
            runner.stop()
            stop_elapsed = time.monotonic() - before_stop

            self.assertLess(stop_elapsed, 0.25)

            deadline = time.monotonic() + 3
            while runner.is_running() and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.001)

            self.assertFalse(runner.is_running())
            self.assertIn("[stop] termino croc...", displayed)
        finally:
            if runner.is_running():
                runner.proc.kill()
                runner.proc.waitForFinished(1000)

    def test_force_stop_kills_a_process_still_running(self) -> None:
        displayed: list[str] = []
        runner = CrocRunner(
            "/nonexistent/croc",
            append_text=lambda _text: None,
            append_line=lambda text="": displayed.append(text),
        )
        process = mock.Mock()
        process.state.return_value = QProcess.ProcessState.Running
        runner._kill_timer.setParent(None)
        runner.proc = process

        runner._force_stop()

        process.kill.assert_called_once_with()
        self.assertIn("[stop] terminazione forzata", displayed)

    def test_stop_does_not_wait_for_process_completion(self) -> None:
        runner = CrocRunner(
            "/nonexistent/croc",
            append_text=lambda _text: None,
            append_line=lambda _text="": None,
        )
        process = mock.Mock()
        process.state.return_value = QProcess.ProcessState.Running
        runner._kill_timer.setParent(None)
        runner.proc = process
        try:
            runner.stop()
        finally:
            runner._kill_timer.stop()

        process.terminate.assert_called_once_with()
        process.waitForFinished.assert_not_called()


if __name__ == "__main__":
    unittest.main()

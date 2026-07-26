from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QMessageBox

from moontransfer.app import ReceiveTab, SendTab
from moontransfer.files import cleanup_session_paths, create_session_paths
from moontransfer.protocol import create_proposal, write_control_file


class _RunnerState:
    def __init__(self, running: bool) -> None:
        self.running = running

    def is_running(self) -> bool:
        return self.running


class _FakeCrocRunner:
    def __init__(
        self,
        _croc_path: str,
        *,
        append_text,
        append_line,
    ) -> None:
        self.append_text = append_text
        self.append_line = append_line
        self.on_line = None
        self.on_finished = None
        self.running = False
        self.starts: list[dict[str, object]] = []
        self.stdin_writes: list[tuple[str, bool]] = []

    def is_running(self) -> bool:
        return self.running

    def start(self, args: list[str], **options) -> None:
        self.running = True
        self.starts.append({"args": args, **options})

    def stop(self) -> None:
        self.running = False

    def write_stdin(self, text: str, *, close: bool = False) -> None:
        self.stdin_writes.append((text, close))

    def emit_line(self, line: str) -> None:
        if self.on_line:
            self.on_line(line)

    def finish(
        self,
        exit_code: int = 0,
        exit_status: QProcess.ExitStatus = QProcess.ExitStatus.NormalExit,
    ) -> None:
        self.running = False
        if self.on_finished:
            self.on_finished(exit_code, exit_status)


class ReceiveFlowSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_rejection_happens_before_destination_hash_check(self) -> None:
        with mock.patch("moontransfer.widgets.QTimer.singleShot"):
            tab = ReceiveTab("/nonexistent/croc")
        proposal = create_proposal(
            filename="example.txt",
            size=7,
            sha256="a" * 64,
        )
        answer_box = mock.Mock()
        answer_box.exec.return_value = QMessageBox.StandardButton.No

        with (
            mock.patch("moontransfer.app.plain_message_box", return_value=answer_box),
            mock.patch("moontransfer.app.check_destination") as check_destination,
        ):
            accepted, target, overwrite = tab._choose_transfer_action(proposal)

        self.assertFalse(accepted)
        self.assertIsNone(target)
        self.assertFalse(overwrite)
        check_destination.assert_not_called()

    def test_receive_monitor_aborts_oversized_metadata(self) -> None:
        with mock.patch("moontransfer.widgets.QTimer.singleShot"):
            tab = ReceiveTab("/nonexistent/croc")
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "destination"
            destination.mkdir()
            paths = create_session_paths(main_receive_parent=destination)
            try:
                (paths.metadata_receive / "oversized.bin").write_bytes(b"1234")
                tab.paths = paths
                tab.session_active = True
                tab.receive_size_limit = 3
                tab.receive_size_stage = "test metadati"
                tab.runners = {
                    "metadata_receive": _RunnerState(True),
                    "main_receive": _RunnerState(False),
                }

                with mock.patch.object(tab, "_abort_session") as abort:
                    tab._check_receive_size()

                abort.assert_called_once()
                self.assertIn(
                    "dimensione superiore",
                    abort.call_args.args[0],
                )
            finally:
                tab.receive_size_timer.stop()
                cleanup_session_paths(paths)


class TransferFlowCharacterizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_send_flow_runs_metadata_then_main_transfer(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
        ):
            source = Path(tmp) / "example.txt"
            source.write_bytes(b"content")
            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = SendTab("/fake/croc")
            tab.file_edit.setText(str(source))

            tab._start_send()
            metadata_runner = tab.runners["metadata_send"]
            main_runner = tab.runners["main_send"]
            session_root = tab.paths.root if tab.paths else None

            self.assertTrue(metadata_runner.is_running())
            self.assertFalse(main_runner.is_running())
            self.assertRegex(tab.code_edit.text(), r"^[0-9a-f]{32}$")

            metadata_runner.finish()
            self.assertTrue(main_runner.is_running())

            main_runner.finish()
            self.assertEqual(tab.status_label.text(), "Invio completato.")
            self.assertFalse(tab.session_active)
            self.assertIsNotNone(session_root)
            assert session_root is not None
            self.assertFalse(session_root.exists())

    def test_receive_accept_flow_verifies_and_saves_file(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
        ):
            destination = Path(tmp) / "destination"
            proposal = create_proposal(
                filename="example.txt",
                size=7,
                sha256=(
                    "ed7002b439e9ac845f22357d822bac1444730fbdb6016d3e"
                    "c9432297b9ec9f73"
                ),
            )
            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = ReceiveTab("/fake/croc")
            tab.code_edit.setText("1" * 32)
            tab.dest_edit.setText(str(destination))
            tab._start_receive()
            assert tab.paths is not None

            metadata_path = (
                tab.paths.metadata_receive / "moontransfer-metadata.json"
            )
            write_control_file(metadata_path, proposal)
            target = destination / proposal.filename

            with (
                mock.patch.object(
                    tab,
                    "_choose_transfer_action",
                    return_value=(True, target, False),
                ),
                mock.patch(
                    "moontransfer.app.QTimer.singleShot",
                    side_effect=lambda _delay, callback: callback(),
                ),
            ):
                tab.runners["metadata_receive"].finish()

            main_runner = tab.runners["main_receive"]
            self.assertTrue(main_runner.is_running())
            self.assertEqual(main_runner.stdin_writes, [("y\n", True)])

            received = tab.paths.main_receive / proposal.filename
            received.write_bytes(b"content")
            main_runner.finish()

            self.assertEqual(target.read_bytes(), b"content")
            self.assertFalse(tab.session_active)
            self.assertIn("Ricezione completata:", tab.status_label.text())

    def test_receive_reject_flow_answers_main_prompt(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
        ):
            destination = Path(tmp) / "destination"
            proposal = create_proposal(
                filename="example.txt",
                size=7,
                sha256="a" * 64,
            )
            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = ReceiveTab("/fake/croc")
            tab.code_edit.setText("2" * 32)
            tab.dest_edit.setText(str(destination))
            tab._start_receive()
            assert tab.paths is not None
            write_control_file(
                tab.paths.metadata_receive / "moontransfer-metadata.json",
                proposal,
            )

            with (
                mock.patch.object(
                    tab,
                    "_choose_transfer_action",
                    return_value=(False, None, False),
                ),
                mock.patch(
                    "moontransfer.app.QTimer.singleShot",
                    side_effect=lambda _delay, callback: callback(),
                ),
            ):
                tab.runners["metadata_receive"].finish()

            main_runner = tab.runners["main_receive"]
            self.assertEqual(main_runner.stdin_writes, [("n\n", True)])
            main_runner.finish()

            self.assertFalse(tab.session_active)
            self.assertEqual(tab.status_label.text(), "Trasferimento rifiutato.")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QMessageBox

from moontransfer.app import ReceiveTab, SendTab
from moontransfer.cancellation import OperationCancelled
from moontransfer.files import cleanup_session_paths, create_session_paths
from moontransfer.protocol import create_proposal, write_control_file
from moontransfer.transfer import (
    ReceiveDecision,
    ReceiveSession,
    TransferState,
)


def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        time.sleep(0.001)
    raise AssertionError("Condizione asincrona non raggiunta entro il timeout.")


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
            mock.patch("moontransfer.transfer.check_destination") as check_destination,
        ):
            accepted = tab._confirm_transfer(proposal)

        self.assertFalse(accepted)
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
                tab.controller.session = ReceiveSession(
                    metadata_code="1" * 32,
                    destination=destination,
                    paths=paths,
                    receive_size_limit=3,
                    receive_size_stage="test metadati",
                )
                tab.controller.machine.state = TransferState.TRANSFERRING_METADATA
                tab.controller.runners = {
                    "metadata_receive": _RunnerState(True),
                    "main_receive": _RunnerState(False),
                }

                with mock.patch.object(
                    tab.controller,
                    "_abort_session",
                ) as abort:
                    tab.controller._check_receive_size()

                abort.assert_called_once()
                self.assertIn(
                    "dimensione superiore",
                    abort.call_args.args[0],
                )
            finally:
                tab.controller.receive_size_timer.stop()
                tab.controller.session = None
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
            _wait_until(metadata_runner.is_running)
            session = tab.controller.session
            session_root = (
                session.paths.root
                if session is not None and session.paths is not None
                else None
            )

            self.assertTrue(metadata_runner.is_running())
            self.assertFalse(main_runner.is_running())
            self.assertRegex(tab.code_edit.text(), r"^[0-9a-f]{32}$")
            self.assertEqual(
                tab.controller.state,
                TransferState.TRANSFERRING_METADATA,
            )

            metadata_runner.finish()
            self.assertTrue(main_runner.is_running())
            self.assertEqual(
                tab.controller.state,
                TransferState.AWAITING_DECISION,
            )

            main_runner.finish()
            self.assertEqual(tab.status_label.text(), "Invio completato.")
            self.assertEqual(
                tab.controller.state,
                TransferState.COMPLETED,
            )
            self.assertFalse(tab.controller.active)
            self.assertIsNotNone(session_root)
            assert session_root is not None
            self.assertFalse(session_root.exists())

    def test_send_failure_cleans_session_and_enters_failed_state(self) -> None:
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
            _wait_until(tab.runners["metadata_send"].is_running)
            session = tab.controller.session
            assert session is not None
            assert session.paths is not None
            session_root = session.paths.root

            tab.runners["metadata_send"].finish(exit_code=1)

            self.assertEqual(tab.controller.state, TransferState.FAILED)
            self.assertFalse(tab.controller.active)
            self.assertIsNone(tab.controller.session)
            self.assertFalse(session_root.exists())

    def test_send_aborts_if_source_changes_after_hashing(self) -> None:
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
            _wait_until(tab.runners["metadata_send"].is_running)
            session = tab.controller.session
            assert session is not None
            assert session.paths is not None
            session_root = session.paths.root

            source.write_bytes(b"changed content")
            with mock.patch("moontransfer.app._show_controller_error"):
                tab.runners["metadata_send"].finish()

            self.assertEqual(tab.controller.state, TransferState.FAILED)
            self.assertFalse(tab.runners["main_send"].is_running())
            self.assertIsNone(tab.controller.session)
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
            session = tab.controller.session
            assert session is not None
            assert session.paths is not None

            metadata_path = (
                session.paths.metadata_receive / "moontransfer-metadata.json"
            )
            write_control_file(metadata_path, proposal)
            target = destination / proposal.filename

            with (
                mock.patch.object(
                    tab,
                    "_confirm_transfer",
                    return_value=True,
                ),
                mock.patch(
                    "moontransfer.transfer.QTimer.singleShot",
                    side_effect=lambda _delay, callback: callback(),
                ),
            ):
                tab.runners["metadata_receive"].finish()
                _wait_until(tab.runners["main_receive"].is_running)

            main_runner = tab.runners["main_receive"]
            self.assertTrue(main_runner.is_running())
            self.assertEqual(main_runner.stdin_writes, [("y\n", True)])
            self.assertEqual(
                tab.controller.state,
                TransferState.TRANSFERRING_FILE,
            )

            received = session.paths.main_receive / proposal.filename
            received.write_bytes(b"content")
            main_runner.finish()
            _wait_until(
                lambda: tab.controller.state == TransferState.COMPLETED
            )

            self.assertEqual(target.read_bytes(), b"content")
            self.assertEqual(
                tab.controller.state,
                TransferState.COMPLETED,
            )
            self.assertFalse(tab.controller.active)
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
            session = tab.controller.session
            assert session is not None
            assert session.paths is not None
            write_control_file(
                session.paths.metadata_receive / "moontransfer-metadata.json",
                proposal,
            )

            with (
                mock.patch.object(
                    tab,
                    "_confirm_transfer",
                    return_value=False,
                ),
                mock.patch(
                    "moontransfer.transfer.QTimer.singleShot",
                    side_effect=lambda _delay, callback: callback(),
                ),
            ):
                tab.runners["metadata_receive"].finish()

            main_runner = tab.runners["main_receive"]
            self.assertEqual(main_runner.stdin_writes, [("n\n", True)])
            main_runner.finish()

            self.assertEqual(
                tab.controller.state,
                TransferState.REJECTED,
            )
            self.assertFalse(tab.controller.active)
            self.assertEqual(tab.status_label.text(), "Trasferimento rifiutato.")

    def test_existing_identical_file_is_resolved_after_async_check(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
        ):
            destination = Path(tmp) / "destination"
            destination.mkdir()
            (destination / "example.txt").write_bytes(b"content")
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
            tab.code_edit.setText("5" * 32)
            tab.dest_edit.setText(str(destination))
            tab._start_receive()
            session = tab.controller.session
            assert session is not None
            assert session.paths is not None
            write_control_file(
                session.paths.metadata_receive / "moontransfer-metadata.json",
                proposal,
            )
            resolver = mock.Mock(return_value=ReceiveDecision.reject())

            with (
                mock.patch.object(
                    tab,
                    "_confirm_transfer",
                    return_value=True,
                ),
                mock.patch.object(
                    tab,
                    "_resolve_destination_conflict",
                    resolver,
                ),
                mock.patch(
                    "moontransfer.transfer.QTimer.singleShot",
                    side_effect=lambda _delay, callback: callback(),
                ),
            ):
                tab.runners["metadata_receive"].finish()
                _wait_until(tab.runners["main_receive"].is_running)

            resolver.assert_called_once()
            check = resolver.call_args.args[1]
            self.assertEqual(check.conflict.value, "identical")
            self.assertEqual(
                tab.runners["main_receive"].stdin_writes,
                [("n\n", True)],
            )
            tab.runners["main_receive"].finish()

            self.assertEqual(tab.controller.state, TransferState.REJECTED)

    def test_receive_stop_cleans_control_and_staging_directories(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
        ):
            destination = Path(tmp) / "destination"
            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = ReceiveTab("/fake/croc")
            tab.code_edit.setText("3" * 32)
            tab.dest_edit.setText(str(destination))
            tab._start_receive()
            session = tab.controller.session
            assert session is not None
            assert session.paths is not None
            session_root = session.paths.root
            staging = session.paths.main_receive

            tab._stop_receive()

            self.assertEqual(tab.controller.state, TransferState.CANCELLED)
            self.assertFalse(tab.controller.active)
            self.assertIsNone(tab.controller.session)
            self.assertFalse(session_root.exists())
            self.assertFalse(staging.exists())

    def test_send_hashing_can_be_cancelled(self) -> None:
        started = Event()

        def blocking_fingerprint(_path, *, cancel_requested):
            started.set()
            while not cancel_requested():
                time.sleep(0.001)
            raise OperationCancelled

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
            mock.patch(
                "moontransfer.transfer.fingerprint_file",
                side_effect=blocking_fingerprint,
            ),
        ):
            source = Path(tmp) / "large.bin"
            source.write_bytes(b"content")
            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = SendTab("/fake/croc")
            tab.file_edit.setText(str(source))

            tab._start_send()
            self.assertTrue(started.wait(timeout=1))
            self.assertEqual(tab.controller.state, TransferState.PREPARING)
            self.assertFalse(tab.runners["metadata_send"].is_running())

            tab._stop_send()

            self.assertEqual(tab.controller.state, TransferState.CANCELLED)
            self.assertFalse(tab.controller.active)
            self.assertIsNone(tab.controller.session)

    def test_destination_check_can_be_cancelled(self) -> None:
        started = Event()

        def blocking_check(_proposal, _destination, *, cancel_requested):
            started.set()
            while not cancel_requested():
                time.sleep(0.001)
            raise OperationCancelled

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
            mock.patch(
                "moontransfer.transfer.check_destination",
                side_effect=blocking_check,
            ),
        ):
            destination = Path(tmp) / "destination"
            proposal = create_proposal(
                filename="example.txt",
                size=7,
                sha256="a" * 64,
            )
            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = ReceiveTab("/fake/croc")
            tab.code_edit.setText("4" * 32)
            tab.dest_edit.setText(str(destination))
            tab._start_receive()
            session = tab.controller.session
            assert session is not None
            assert session.paths is not None
            write_control_file(
                session.paths.metadata_receive / "moontransfer-metadata.json",
                proposal,
            )

            with mock.patch.object(
                tab,
                "_confirm_transfer",
                return_value=True,
            ):
                tab.runners["metadata_receive"].finish()
                self.assertTrue(started.wait(timeout=1))

            self.assertEqual(
                tab.controller.state,
                TransferState.CHECKING_DESTINATION,
            )
            tab._stop_receive()

            self.assertEqual(tab.controller.state, TransferState.CANCELLED)
            self.assertFalse(tab.controller.active)
            self.assertIsNone(tab.controller.session)

    def test_received_file_verification_can_be_cancelled(self) -> None:
        started = Event()

        def blocking_verify(_path, _proposal, *, cancel_requested):
            started.set()
            while not cancel_requested():
                time.sleep(0.001)
            raise OperationCancelled

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
            tab.code_edit.setText("6" * 32)
            tab.dest_edit.setText(str(destination))
            tab._start_receive()
            session = tab.controller.session
            assert session is not None
            assert session.paths is not None
            write_control_file(
                session.paths.metadata_receive / "moontransfer-metadata.json",
                proposal,
            )

            with (
                mock.patch.object(
                    tab,
                    "_confirm_transfer",
                    return_value=True,
                ),
                mock.patch(
                    "moontransfer.transfer.QTimer.singleShot",
                    side_effect=lambda _delay, callback: callback(),
                ),
            ):
                tab.runners["metadata_receive"].finish()
                _wait_until(tab.runners["main_receive"].is_running)

            received = session.paths.main_receive / proposal.filename
            received.write_bytes(b"content")
            session_root = session.paths.root
            staging = session.paths.main_receive
            with mock.patch(
                "moontransfer.transfer.verify_received_file",
                side_effect=blocking_verify,
            ):
                tab.runners["main_receive"].finish()
                self.assertTrue(started.wait(timeout=1))
                self.assertEqual(
                    tab.controller.state,
                    TransferState.VERIFYING,
                )
                tab._stop_receive()

            self.assertEqual(tab.controller.state, TransferState.CANCELLED)
            self.assertFalse(session_root.exists())
            self.assertFalse(staging.exists())

    def test_completed_save_wins_over_late_stop_request(self) -> None:
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
            tab.code_edit.setText("7" * 32)
            tab.dest_edit.setText(str(destination))
            tab._start_receive()
            session = tab.controller.session
            assert session is not None
            assert session.paths is not None
            write_control_file(
                session.paths.metadata_receive / "moontransfer-metadata.json",
                proposal,
            )

            with (
                mock.patch.object(
                    tab,
                    "_confirm_transfer",
                    return_value=True,
                ),
                mock.patch(
                    "moontransfer.transfer.QTimer.singleShot",
                    side_effect=lambda _delay, callback: callback(),
                ),
            ):
                tab.runners["metadata_receive"].finish()
                _wait_until(tab.runners["main_receive"].is_running)

            received = session.paths.main_receive / proposal.filename
            received.write_bytes(b"content")
            tab.runners["main_receive"].finish()
            task = tab.controller._task
            assert task is not None
            self.assertTrue(task.wait(1000))
            self.assertEqual(tab.controller.state, TransferState.VERIFYING)

            tab._stop_receive()

            self.assertEqual(tab.controller.state, TransferState.COMPLETED)
            self.assertEqual(
                (destination / proposal.filename).read_bytes(),
                b"content",
            )


if __name__ == "__main__":
    unittest.main()

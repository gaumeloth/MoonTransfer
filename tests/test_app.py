from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPoint, QPointF, QProcess, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from moontransfer.app import (
    MainWindow,
    ReceiveTab,
    SendTab,
    configure_application,
)
from moontransfer.build_info import CURRENT_BUILD
from moontransfer.cancellation import OperationCancelled
from moontransfer.files import cleanup_session_paths, create_session_paths
from moontransfer.payload import scan_source_payload
from moontransfer.protocol import create_proposal, write_control_file
from moontransfer.resources import APP_ICON_PATH
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


class _DeferredStopCrocRunner(_FakeCrocRunner):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.stop_requested = False

    def stop(self) -> None:
        if self.running:
            self.stop_requested = True


class ApplicationConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_application_icon_is_available_and_loadable(self) -> None:
        configure_application(self.app)

        self.assertTrue(APP_ICON_PATH.is_file())
        self.assertEqual(self.app.applicationName(), "MoonTransfer")
        self.assertEqual(self.app.applicationVersion(), CURRENT_BUILD.version)
        self.assertFalse(self.app.windowIcon().isNull())

    def test_main_window_uses_the_application_icon_explicitly(self) -> None:
        configure_application(self.app)

        with (
            mock.patch(
                "moontransfer.app.croc.find_executable",
                return_value="/fake/croc",
            ),
            mock.patch("moontransfer.widgets.QTimer.singleShot"),
        ):
            window = MainWindow()

        try:
            self.assertFalse(window.windowIcon().isNull())
            self.assertTrue(window.windowIcon().availableSizes())
            self.assertIn(CURRENT_BUILD.version, window.windowTitle())
            self.assertEqual(
                window.build_info_button.toolTip(),
                "Informazioni sulla build",
            )
        finally:
            window.close()

    def test_build_diagnostics_can_be_copied(self) -> None:
        class FakeMessageBox:
            def __init__(self) -> None:
                self.copy_button = object()

            def addButton(self, *_args: object) -> object:
                return self.copy_button

            def exec(self) -> None:
                return None

            def clickedButton(self) -> object:
                return self.copy_button

        fake_box = FakeMessageBox()
        with (
            mock.patch(
                "moontransfer.app.croc.find_executable",
                return_value="/fake/croc",
            ),
            mock.patch(
                "moontransfer.app.plain_message_box",
                return_value=fake_box,
            ),
            mock.patch("moontransfer.widgets.QTimer.singleShot"),
        ):
            window = MainWindow()
            window._show_build_info()

        try:
            self.assertEqual(
                QApplication.clipboard().text(),
                CURRENT_BUILD.diagnostics(),
            )
        finally:
            window.close()


class SendTabSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_dropped_paths_use_the_existing_selection_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_file = Path(tmp) / "note.txt"
            source_folder = Path(tmp) / "photos"
            source_file.write_text("note", encoding="utf-8")
            source_folder.mkdir()
            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = SendTab("/fake/croc")

            mime_data = QMimeData()
            mime_data.setUrls(
                [
                    QUrl.fromLocalFile(str(source_file)),
                    QUrl.fromLocalFile(str(source_folder)),
                    QUrl.fromLocalFile(str(source_file)),
                ]
            )
            enter_event = QDragEnterEvent(
                QPoint(1, 1),
                Qt.DropAction.CopyAction,
                mime_data,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.sendEvent(
                tab.source_list.viewport(),
                enter_event,
            )
            drop_event = QDropEvent(
                QPointF(1, 1),
                Qt.DropAction.CopyAction,
                mime_data,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.sendEvent(tab.source_list.viewport(), drop_event)

            self.assertTrue(enter_event.isAccepted())
            self.assertTrue(drop_event.isAccepted())
            self.assertEqual(
                tab.source_paths,
                [source_file, source_folder],
            )
            self.assertEqual(tab.source_list.count(), 2)
            self.assertTrue(tab.start_button.isEnabled())

    def test_drop_is_disabled_while_a_transfer_is_active(self) -> None:
        with mock.patch("moontransfer.widgets.QTimer.singleShot"):
            tab = SendTab("/fake/croc")

        self.assertTrue(tab.source_list.drop_enabled)

        tab._set_running(True)

        self.assertFalse(tab.source_list.drop_enabled)
        self.assertFalse(tab.source_list.isEnabled())

    def test_selection_limit_rejects_the_whole_new_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.txt"
            second = Path(tmp) / "second.txt"
            first.touch()
            second.touch()
            with (
                mock.patch("moontransfer.app.MAX_PAYLOAD_ROOTS", 1),
                mock.patch("moontransfer.widgets.QTimer.singleShot"),
            ):
                tab = SendTab("/fake/croc")
                tab._add_paths((first, second))

            self.assertEqual(tab.source_paths, [])
            self.assertEqual(tab.source_list.count(), 0)
            self.assertIn("al massimo 1", tab.status_label.text())


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
            mock.patch(
                "moontransfer.transfer.check_payload_destination"
            ) as check_destination,
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
            tab._add_paths((source,))

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
            _wait_until(main_runner.is_running)
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

    def test_send_flow_passes_multiple_roots_to_one_main_process(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
        ):
            base = Path(tmp)
            source_file = base / "note.txt"
            source_folder = base / "photos"
            empty_folder = source_folder / "empty"
            source_file.write_text("note", encoding="utf-8")
            empty_folder.mkdir(parents=True)
            (source_folder / "image.bin").write_bytes(b"image")

            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = SendTab("/fake/croc")
            tab._add_paths((source_file, source_folder))
            tab._start_send()

            metadata_runner = tab.runners["metadata_send"]
            main_runner = tab.runners["main_send"]
            _wait_until(metadata_runner.is_running)
            session = tab.controller.session
            assert session is not None
            assert session.proposal is not None

            self.assertEqual(session.proposal.roots, ("note.txt", "photos"))
            self.assertEqual(session.proposal.file_count, 2)
            self.assertEqual(session.proposal.directory_count, 2)
            self.assertIn(
                "photos/empty",
                {entry.path for entry in session.proposal.entries},
            )

            metadata_runner.finish()
            _wait_until(main_runner.is_running)
            main_args = main_runner.starts[-1]["args"]
            self.assertEqual(
                main_args[-2:],
                [str(source_file.resolve()), str(source_folder.resolve())],
            )

            main_runner.finish()
            self.assertEqual(tab.controller.state, TransferState.COMPLETED)

    def test_receive_flow_verifies_and_publishes_multiple_roots(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
        ):
            base = Path(tmp)
            source_file = base / "note.txt"
            source_folder = base / "photos"
            source_file.write_text("note", encoding="utf-8")
            (source_folder / "empty").mkdir(parents=True)
            (source_folder / "image.bin").write_bytes(b"image")
            proposal = scan_source_payload(
                (source_file, source_folder)
            ).create_proposal()

            destination = base / "destination"
            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = ReceiveTab("/fake/croc")
            tab.code_edit.setText("8" * 32)
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

            staging = session.paths.main_receive
            (staging / "note.txt").write_text("note", encoding="utf-8")
            received_folder = staging / "photos"
            (received_folder / "empty").mkdir(parents=True)
            (received_folder / "image.bin").write_bytes(b"image")
            tab.runners["main_receive"].finish()
            _wait_until(
                lambda: tab.controller.state == TransferState.COMPLETED
            )

            target = destination / "MoonTransfer"
            self.assertEqual(
                (target / "note.txt").read_text(encoding="utf-8"),
                "note",
            )
            self.assertEqual(
                (target / "photos" / "image.bin").read_bytes(),
                b"image",
            )
            self.assertTrue((target / "photos" / "empty").is_dir())
            self.assertFalse(staging.exists())

    def test_send_failure_cleans_session_and_enters_failed_state(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
        ):
            source = Path(tmp) / "example.txt"
            source.write_bytes(b"content")
            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = SendTab("/fake/croc")
            tab._add_paths((source,))
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
            tab._add_paths((source,))
            tab._start_send()
            _wait_until(tab.runners["metadata_send"].is_running)
            session = tab.controller.session
            assert session is not None
            assert session.paths is not None
            session_root = session.paths.root

            source.write_bytes(b"changed content")
            with mock.patch("moontransfer.app._show_controller_error"):
                tab.runners["metadata_send"].finish()
                _wait_until(
                    lambda: tab.controller.state == TransferState.FAILED
                )

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
        release = Event()

        def blocking_scan(_paths, *, cancel_requested):
            started.set()
            release.wait(timeout=2)
            if cancel_requested():
                raise OperationCancelled
            raise AssertionError("Il worker non ha ricevuto la cancellazione.")

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
            mock.patch(
                "moontransfer.transfer.scan_source_payload",
                side_effect=blocking_scan,
            ),
        ):
            source = Path(tmp) / "large.bin"
            source.write_bytes(b"content")
            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = SendTab("/fake/croc")
            tab._add_paths((source,))

            tab._start_send()
            self.assertTrue(started.wait(timeout=1))
            self.assertEqual(tab.controller.state, TransferState.PREPARING)
            self.assertFalse(tab.runners["metadata_send"].is_running())

            before_stop = time.monotonic()
            tab._stop_send()
            stop_elapsed = time.monotonic() - before_stop

            self.assertLess(stop_elapsed, 0.25)
            self.assertEqual(tab.controller.state, TransferState.PREPARING)
            self.assertTrue(tab.controller.busy)
            self.assertIsNotNone(tab.controller.session)

            release.set()
            _wait_until(
                lambda: tab.controller.state == TransferState.CANCELLED
            )
            self.assertEqual(tab.controller.state, TransferState.CANCELLED)
            self.assertFalse(tab.controller.active)
            self.assertIsNone(tab.controller.session)

    def test_send_stop_waits_for_process_before_cleanup(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch(
                "moontransfer.app.CrocRunner",
                _DeferredStopCrocRunner,
            ),
        ):
            source = Path(tmp) / "example.txt"
            source.write_bytes(b"content")
            with mock.patch("moontransfer.widgets.QTimer.singleShot"):
                tab = SendTab("/fake/croc")
            tab._add_paths((source,))
            tab._start_send()

            metadata_runner = tab.runners["metadata_send"]
            _wait_until(metadata_runner.is_running)
            session = tab.controller.session
            assert session is not None
            assert session.paths is not None
            session_root = session.paths.root

            tab._stop_send()

            self.assertTrue(metadata_runner.stop_requested)
            self.assertTrue(tab.controller.busy)
            self.assertIs(tab.controller.session, session)
            self.assertTrue(session_root.exists())

            metadata_runner.finish(
                exit_code=15,
                exit_status=QProcess.ExitStatus.CrashExit,
            )

            self.assertEqual(tab.controller.state, TransferState.CANCELLED)
            self.assertFalse(tab.controller.busy)
            self.assertIsNone(tab.controller.session)
            self.assertFalse(session_root.exists())

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
                "moontransfer.transfer.check_payload_destination",
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

            _wait_until(
                lambda: tab.controller.state == TransferState.CANCELLED
            )
            self.assertEqual(tab.controller.state, TransferState.CANCELLED)
            self.assertFalse(tab.controller.active)
            self.assertIsNone(tab.controller.session)

    def test_received_file_verification_can_be_cancelled(self) -> None:
        started = Event()

        def blocking_verify(_staging, _proposal, *, cancel_requested):
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
                "moontransfer.transfer.verify_received_payload",
                side_effect=blocking_verify,
            ):
                tab.runners["main_receive"].finish()
                self.assertTrue(started.wait(timeout=1))
                self.assertEqual(
                    tab.controller.state,
                    TransferState.VERIFYING,
                )
                tab._stop_receive()

            _wait_until(
                lambda: tab.controller.state == TransferState.CANCELLED
            )
            self.assertEqual(tab.controller.state, TransferState.CANCELLED)
            self.assertFalse(session_root.exists())
            self.assertFalse(staging.exists())

    def test_window_close_waits_for_active_worker(self) -> None:
        started = Event()
        release = Event()

        def blocking_scan(_paths, *, cancel_requested):
            started.set()
            release.wait(timeout=2)
            if cancel_requested():
                raise OperationCancelled
            raise AssertionError("Il worker non ha ricevuto la cancellazione.")

        window = None
        try:
            with (
                tempfile.TemporaryDirectory() as tmp,
                mock.patch("moontransfer.app.CrocRunner", _FakeCrocRunner),
                mock.patch(
                    "moontransfer.app.croc.find_executable",
                    return_value="/fake/croc",
                ),
                mock.patch(
                    "moontransfer.transfer.scan_source_payload",
                    side_effect=blocking_scan,
                ),
            ):
                source = Path(tmp) / "large.bin"
                source.write_bytes(b"content")
                window = MainWindow()
                window.send_tab._add_paths((source,))
                window.show()
                QApplication.processEvents()

                window.send_tab._start_send()
                self.assertTrue(started.wait(timeout=1))

                self.assertFalse(window.close())
                self.assertTrue(window.isVisible())
                self.assertTrue(window._close_pending)
                self.assertTrue(window.send_tab.controller.busy)

                release.set()
                _wait_until(lambda: not window.isVisible())

                self.assertFalse(window.send_tab.controller.busy)
                self.assertEqual(
                    window.send_tab.controller.state,
                    TransferState.CANCELLED,
                )
                self.assertIsNone(window.send_tab.controller.session)
        finally:
            release.set()
            if window is not None and window.send_tab.controller.busy:
                window.send_tab.controller.stop()
                _wait_until(lambda: not window.send_tab.controller.busy)
            if window is not None:
                window.close()

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

            _wait_until(
                lambda: tab.controller.state == TransferState.COMPLETED
            )
            self.assertEqual(tab.controller.state, TransferState.COMPLETED)
            self.assertEqual(
                (destination / proposal.filename).read_bytes(),
                b"content",
            )


if __name__ == "__main__":
    unittest.main()

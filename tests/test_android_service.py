from __future__ import annotations

import io
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
ANDROID_APP = ROOT / "android" / "app"
sys.path.insert(0, str(ANDROID_APP))

from moontransfer.cancellation import OperationCancelled  # noqa: E402
from moontransfer.files import CONTROL_METADATA_NAME  # noqa: E402
from moontransfer.progress import TransferProgressSample  # noqa: E402
from moontransfer.protocol import (  # noqa: E402
    PayloadEntry,
    create_payload_proposal,
    create_proposal,
    write_control_file,
)
from moontransfer_android.android_runtime import (  # noqa: E402
    AndroidRuntimeError,
    TransferNotification,
    _start_service_intent,
)
from moontransfer_android.service_client import (  # noqa: E402
    TransferServiceClient,
    TransferServiceHeartbeatMonitor,
    recover_latest_service_client,
)
from moontransfer_android.service_protocol import (  # noqa: E402
    TransferServiceCommandName,
    TransferServiceError,
    TransferServiceOperation,
    TransferServiceStateStore,
    _read_summary,
    _replace_file_atomic,
    consume_service_commands,
    create_receive_service_request,
    create_send_service_request,
    discover_service_requests,
    read_service_request,
    read_service_snapshot,
    service_session_dir,
    staged_document_from_request,
    staged_selection_from_request,
    submit_service_command,
)
from moontransfer_android.storage import (  # noqa: E402
    StagedDocument,
    StagedSelection,
)
from moontransfer_android.transfer_service import (  # noqa: E402
    TransferServiceRuntime,
    build_transfer_notification,
    build_transfer_result_notification,
)
from moontransfer_android.transport import CrocProcessResult  # noqa: E402


def _stage_file(cache_root: Path, content: bytes = b"payload") -> StagedDocument:
    staging_dir = cache_root / "staging" / "document"
    staging_dir.mkdir(parents=True)
    path = staging_dir / "example.bin"
    path.write_bytes(content)
    return StagedDocument(
        path=path,
        staging_dir=staging_dir,
        filename=path.name,
        size=len(content),
    )


def _wait_for_state(
    cache_root: Path,
    session_id: str,
    expected: str,
    *,
    timeout: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout
    last_state = "unknown"
    last_status = "unknown"
    while time.monotonic() < deadline:
        snapshot = read_service_snapshot(cache_root, session_id)
        last_state = snapshot.state
        last_status = snapshot.status
        if last_state == expected:
            return
        time.sleep(0.01)
    raise AssertionError(
        f"service did not enter state {expected}; last state was {last_state}; "
        f"last status was {last_status}"
    )


class _ServiceStartContext:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, object]] = []

    def startForegroundService(self, intent: object) -> None:
        self.calls.append(("foreground", intent))
        if self.fail:
            raise RuntimeError("start denied")

    def startService(self, intent: object) -> None:
        self.calls.append(("service", intent))
        if self.fail:
            raise RuntimeError("start denied")


class _SuccessfulSendRunner:
    def __init__(self, *, block_main: bool = False) -> None:
        self.block_main = block_main
        self.calls: list[dict[str, object]] = []
        self.stop_requested = False
        self.metadata_finished = threading.Event()

    def run(
        self,
        args: list[str],
        *,
        config_dir: Path,
        secret: str,
        workdir: Path | None,
        idle_timeout: float,
        cancel_requested: object,
        on_line: object,
        stdin_data: bytes | None = None,
        process_guard: object = None,
    ) -> CrocProcessResult:
        self.calls.append({"args": args, "secret": secret})
        is_metadata = str(args[-1]).endswith(CONTROL_METADATA_NAME)
        if is_metadata:
            on_line("Code is: <hidden>")  # type: ignore[operator]
            if process_guard:
                process_guard()  # type: ignore[operator]
            self.metadata_finished.set()
            return CrocProcessResult(returncode=0, output_tail=())
        on_line("Code is: <hidden>")  # type: ignore[operator]
        if self.block_main:
            while not cancel_requested():  # type: ignore[operator]
                time.sleep(0.01)
            raise OperationCancelled
        self.metadata_finished.wait(2)
        on_line("Sending (->127.0.0.1:9009)")  # type: ignore[operator]
        on_line("example.bin 100% | (7 B/7 B, 1 KB/s)")  # type: ignore[operator]
        return CrocProcessResult(returncode=0, output_tail=())

    def request_stop(self) -> None:
        self.stop_requested = True


class _RejectableReceiveRunner:
    def __init__(self) -> None:
        self.proposal = create_proposal(
            filename="example.bin",
            size=7,
            sha256=(
                "239f59ed55e737c77147cf55ad0c1b030"
                "b6d7ee748a7426952f9b852d5a935e5"
            ),
        )
        self.calls: list[bytes | None] = []

    def run(
        self,
        _args: list[str],
        *,
        config_dir: Path,
        secret: str,
        workdir: Path | None,
        idle_timeout: float,
        cancel_requested: object,
        on_line: object,
        stdin_data: bytes | None = None,
        process_guard: object = None,
    ) -> CrocProcessResult:
        del config_dir, secret, idle_timeout, cancel_requested, on_line
        if workdir is None:
            raise AssertionError("workdir is required")
        self.calls.append(stdin_data)
        if len(self.calls) == 1:
            write_control_file(workdir / CONTROL_METADATA_NAME, self.proposal)
            if process_guard:
                process_guard()  # type: ignore[operator]
        return CrocProcessResult(returncode=0, output_tail=())

    def request_stop(self) -> None:
        return None


class AndroidServiceProtocolTests(unittest.TestCase):
    def test_atomic_replace_retries_windows_reader_contention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            destination = root / "destination.json"
            source.write_text("new", encoding="ascii")
            destination.write_text("old", encoding="ascii")
            real_replace = os.replace
            attempts = 0

            def replace_after_contention(
                source_path: Path,
                destination_path: Path,
            ) -> None:
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError("destination is being read")
                real_replace(source_path, destination_path)

            with (
                mock.patch(
                    "moontransfer_android.service_protocol.os.replace",
                    side_effect=replace_after_contention,
                ),
                mock.patch(
                    "moontransfer_android.service_protocol.time.sleep"
                ) as sleep,
            ):
                _replace_file_atomic(source, destination, windows=True)

            self.assertEqual(attempts, 2)
            sleep.assert_called_once_with(0.01)
            self.assertEqual(destination.read_text(encoding="ascii"), "new")

    def test_atomic_replace_does_not_retry_other_platforms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            destination = root / "destination.json"
            source.write_text("new", encoding="ascii")

            with mock.patch(
                "moontransfer_android.service_protocol.os.replace",
                side_effect=PermissionError("access denied"),
            ) as replace_file:
                with self.assertRaises(PermissionError):
                    _replace_file_atomic(source, destination, windows=False)

            replace_file.assert_called_once_with(source, destination)

    def test_atomic_replace_stops_at_windows_retry_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            destination = root / "destination.json"
            source.write_text("new", encoding="ascii")

            with (
                mock.patch(
                    "moontransfer_android.service_protocol.os.replace",
                    side_effect=PermissionError("access denied"),
                ) as replace_file,
                mock.patch(
                    "moontransfer_android.service_protocol.time.monotonic",
                    side_effect=(10.0, 11.0),
                ),
                mock.patch(
                    "moontransfer_android.service_protocol.time.sleep"
                ) as sleep,
            ):
                with self.assertRaises(PermissionError):
                    _replace_file_atomic(source, destination, windows=True)

            replace_file.assert_called_once_with(source, destination)
            sleep.assert_not_called()

    def test_service_start_uses_api_appropriate_android_method(self) -> None:
        modern = _ServiceStartContext()
        legacy = _ServiceStartContext()
        intent = object()

        _start_service_intent(modern, intent, 35)
        _start_service_intent(legacy, intent, 24)

        self.assertEqual(modern.calls, [("foreground", intent)])
        self.assertEqual(legacy.calls, [("service", intent)])

    def test_service_start_denial_has_a_stable_user_message(self) -> None:
        context = _ServiceStartContext(fail=True)

        with self.assertRaisesRegex(
            AndroidRuntimeError,
            "Android non ha consentito.*Mantieni MoonTransfer visibile",
        ):
            _start_service_intent(context, object(), 35)

    def test_send_request_uses_private_relative_paths_and_secure_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            document = _stage_file(cache_root)

            created = create_send_service_request(cache_root, document)
            restored = read_service_request(cache_root, created.session_id)
            restored_document = staged_document_from_request(cache_root, restored)
            snapshot = read_service_snapshot(cache_root, created.session_id)

            self.assertEqual(restored.operation, TransferServiceOperation.SEND)
            self.assertFalse(Path(restored.document_path or "").is_absolute())
            self.assertEqual(
                restored_document.path,
                document.path.resolve(strict=True),
            )
            self.assertEqual(
                restored_document.staging_dir,
                document.staging_dir.resolve(strict=True),
            )
            self.assertEqual(restored_document.filename, document.filename)
            self.assertEqual(restored_document.size, document.size)
            self.assertEqual(snapshot.state, "preparing")
            if os.name != "nt":
                session_dir = service_session_dir(cache_root, created.session_id)
                self.assertEqual(stat.S_IMODE(session_dir.stat().st_mode), 0o700)
                self.assertEqual(
                    stat.S_IMODE((session_dir / "request.json").stat().st_mode),
                    0o600,
                )

    def test_send_request_round_trips_multiple_private_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            documents: list[StagedDocument] = []
            for index, content in enumerate((b"first", b"second"), start=1):
                staging_dir = cache_root / "staging" / f"document-{index}"
                staging_dir.mkdir(parents=True)
                path = staging_dir / f"file-{index}.bin"
                path.write_bytes(content)
                documents.append(
                    StagedDocument(
                        path=path,
                        staging_dir=staging_dir,
                        filename=path.name,
                        size=len(content),
                    )
                )
            selection = StagedSelection(tuple(documents))

            created = create_send_service_request(cache_root, selection)
            restored = read_service_request(cache_root, created.session_id)
            restored_selection = staged_selection_from_request(
                cache_root,
                restored,
            )

            self.assertEqual(restored.filename, "MoonTransfer")
            self.assertEqual(restored.size, 11)
            self.assertIsNone(restored.document_path)
            self.assertIsNone(restored.staging_dir)
            self.assertEqual(len(restored.documents), 2)
            self.assertEqual(restored_selection.filenames, selection.filenames)
            self.assertEqual(
                restored_selection.total_size,
                selection.total_size,
            )
            self.assertEqual(
                restored_selection.root_paths,
                tuple(path.resolve(strict=True) for path in selection.root_paths),
            )

    def test_multi_file_proposal_summary_survives_service_state_round_trip(
        self,
    ) -> None:
        proposal = create_payload_proposal(
            roots=("first.txt", "second.txt"),
            entries=(
                PayloadEntry(
                    path="first.txt",
                    type="file",
                    size=1,
                    sha256="a" * 64,
                ),
                PayloadEntry(
                    path="second.txt",
                    type="file",
                    size=2,
                    sha256="b" * 64,
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            request = create_receive_service_request(cache_root, "a" * 32)
            state = TransferServiceStateStore(cache_root, request)

            state.set_proposal(proposal)
            summary = read_service_snapshot(
                cache_root,
                request.session_id,
            ).proposal

            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertEqual(summary.filename, "MoonTransfer")
            self.assertEqual(summary.roots, proposal.roots)
            self.assertEqual(summary.file_count, 2)
            self.assertEqual(summary.directory_count, 0)
            self.assertFalse(summary.is_single_file)
            self.assertIsNone(summary.sha256)

    def test_legacy_single_file_summary_remains_readable(self) -> None:
        summary = _read_summary(
            {
                "filename": "example.bin",
                "size": 7,
                "sha256": (
                    "239f59ed55e737c77147cf55ad0c1b030"
                    "b6d7ee748a7426952f9b852d5a935e5"
                ),
                "is_single_file": True,
            }
        )

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.roots, ("example.bin",))
        self.assertEqual(summary.file_count, 1)
        self.assertEqual(summary.directory_count, 0)

    def test_send_request_rejects_files_outside_private_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / "cache"
            cache_root.mkdir()
            document = _stage_file(root / "outside")

            with self.assertRaisesRegex(
                TransferServiceError,
                "cache privata",
            ):
                create_send_service_request(cache_root, document)

    def test_commands_are_validated_and_consumed_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            request = create_receive_service_request(cache_root, "a" * 32)

            submit_service_command(
                cache_root,
                request.session_id,
                TransferServiceCommandName.ACCEPT,
            )
            submit_service_command(
                cache_root,
                request.session_id,
                TransferServiceCommandName.SAVE,
                destination_uri="content://provider/document/1",
            )
            commands = consume_service_commands(cache_root, request.session_id)

            self.assertEqual(
                [command.command for command in commands],
                [
                    TransferServiceCommandName.ACCEPT,
                    TransferServiceCommandName.SAVE,
                ],
            )
            self.assertEqual(
                commands[1].destination_uri,
                "content://provider/document/1",
            )
            self.assertEqual(
                consume_service_commands(cache_root, request.session_id),
                (),
            )
            with self.assertRaisesRegex(TransferServiceError, "Destinazione"):
                submit_service_command(
                    cache_root,
                    request.session_id,
                    TransferServiceCommandName.SAVE,
                    destination_uri="file:///tmp/output",
                )

    def test_terminal_send_request_can_be_recovered_after_staging_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            document = _stage_file(cache_root)
            request = create_send_service_request(cache_root, document)
            document.path.unlink()
            document.staging_dir.rmdir()

            restored = read_service_request(cache_root, request.session_id)

            self.assertEqual(restored.filename, document.filename)
            with self.assertRaisesRegex(TransferServiceError, "Percorso privato"):
                staged_document_from_request(cache_root, restored)

    def test_client_recovers_latest_session_and_cleans_it_idempotently(self) -> None:
        starts: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            client = TransferServiceClient.for_receive(
                cache_root,
                "b" * 32,
                service_starter=lambda session_id, description: starts.append(
                    (session_id, description)
                ),
            )
            client.start()

            recovered, snapshot = recover_latest_service_client(cache_root)

            self.assertEqual(starts, [(client.session_id, "Ricezione in corso")])
            self.assertIsNotNone(recovered)
            self.assertIsNotNone(snapshot)
            assert recovered is not None
            self.assertEqual(recovered.session_id, client.session_id)
            client.cleanup()
            client.cleanup()
            self.assertEqual(recover_latest_service_client(cache_root), (None, None))

    def test_recovery_keeps_the_latest_request_when_its_state_is_unreadable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            older = create_receive_service_request(cache_root, "b" * 32)
            latest = create_receive_service_request(cache_root, "c" * 32)
            older_dir = service_session_dir(cache_root, older.session_id)
            latest_dir = service_session_dir(cache_root, latest.session_id)
            os.utime(older_dir, ns=(100, 100))
            os.utime(latest_dir, ns=(200, 200))
            (latest_dir / "state.json").write_text("{", encoding="ascii")

            requests = discover_service_requests(cache_root)
            recovered, snapshot = recover_latest_service_client(cache_root)

            self.assertEqual(
                [request.session_id for request in requests],
                [latest.session_id, older.session_id],
            )
            self.assertIsNotNone(recovered)
            assert recovered is not None
            self.assertEqual(recovered.session_id, latest.session_id)
            self.assertIsNone(snapshot)

    def test_client_delegates_forced_service_stop(self) -> None:
        stopped: list[bool] = []
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            client = TransferServiceClient.for_receive(
                cache_root,
                "b" * 32,
                service_stopper=lambda: stopped.append(True),
            )

            client.stop()

            self.assertEqual(stopped, [True])

    def test_heartbeat_monitor_times_out_only_after_missed_updates(self) -> None:
        now = [10.0]
        monitor = TransferServiceHeartbeatMonitor(
            timeout_seconds=5.0,
            clock=lambda: now[0],
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            request = create_receive_service_request(cache_root, "c" * 32)
            snapshot = read_service_snapshot(cache_root, request.session_id)

            self.assertFalse(monitor.timed_out(snapshot))
            now[0] = 14.9
            self.assertFalse(monitor.timed_out(snapshot))
            now[0] = 15.0
            self.assertTrue(monitor.timed_out(snapshot))

            refreshed = replace(
                snapshot,
                heartbeat_ns=snapshot.heartbeat_ns + 1,
            )
            self.assertFalse(monitor.timed_out(refreshed))

    def test_completed_service_never_times_out(self) -> None:
        now = [0.0]
        monitor = TransferServiceHeartbeatMonitor(
            timeout_seconds=1.0,
            clock=lambda: now[0],
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            request = create_receive_service_request(cache_root, "c" * 32)
            snapshot = read_service_snapshot(cache_root, request.session_id)

            self.assertFalse(monitor.timed_out(snapshot))
            now[0] = 2.0
            self.assertFalse(
                monitor.timed_out(replace(snapshot, service_done=True))
            )

    def test_unavailable_snapshot_uses_a_separate_bounded_grace_period(self) -> None:
        now = [10.0]
        monitor = TransferServiceHeartbeatMonitor(
            timeout_seconds=5.0,
            snapshot_unavailable_timeout_seconds=3.0,
            clock=lambda: now[0],
        )

        self.assertFalse(monitor.snapshot_unavailable_timed_out())
        now[0] = 12.9
        self.assertFalse(monitor.snapshot_unavailable_timed_out())
        now[0] = 13.0
        self.assertTrue(monitor.snapshot_unavailable_timed_out())

        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            request = create_receive_service_request(cache_root, "c" * 32)
            snapshot = read_service_snapshot(cache_root, request.session_id)
            self.assertFalse(monitor.timed_out(snapshot))

        now[0] = 20.0
        self.assertFalse(monitor.snapshot_unavailable_timed_out())


class AndroidTransferServiceRuntimeTests(unittest.TestCase):
    def test_service_owns_successful_send_until_terminal_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            document = _stage_file(cache_root)
            request = create_send_service_request(cache_root, document)
            runner = _SuccessfulSendRunner()
            notifications: list[TransferNotification] = []
            results: list[TransferNotification] = []
            runtime = TransferServiceRuntime(
                cache_root,
                runner_factory=lambda: runner,  # type: ignore[arg-type]
                notification_updater=notifications.append,
                result_notifier=results.append,
                sleep=lambda _seconds: time.sleep(0.001),
            )

            runtime.run(request.session_id)
            snapshot = read_service_snapshot(cache_root, request.session_id)

            self.assertEqual(snapshot.state, "completed")
            self.assertTrue(snapshot.terminal)
            self.assertTrue(snapshot.service_done)
            self.assertIsNotNone(snapshot.code)
            self.assertEqual(snapshot.progress.percent, 100)  # type: ignore[union-attr]
            self.assertFalse(document.staging_dir.exists())
            self.assertTrue(
                any(item.title == "Invio completato" for item in notifications)
            )
            self.assertTrue(
                any(
                    item.cancel_session_id == request.session_id
                    for item in notifications
                )
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "Invio completato")
            self.assertIn("example.bin", results[0].text)
            self.assertIsNone(results[0].cancel_session_id)

    def test_service_consumes_cancel_command_for_blocked_sender(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            request = create_send_service_request(
                cache_root,
                _stage_file(cache_root),
            )
            runner = _SuccessfulSendRunner(block_main=True)
            results: list[TransferNotification] = []
            runtime = TransferServiceRuntime(
                cache_root,
                runner_factory=lambda: runner,  # type: ignore[arg-type]
                notification_updater=lambda _message: None,
                result_notifier=results.append,
                sleep=lambda _seconds: time.sleep(0.001),
            )
            thread = threading.Thread(
                target=runtime.run,
                args=(request.session_id,),
            )
            thread.start()
            _wait_for_state(cache_root, request.session_id, "awaiting_decision")

            submit_service_command(
                cache_root,
                request.session_id,
                TransferServiceCommandName.CANCEL,
            )
            thread.join(10)

            self.assertFalse(thread.is_alive())
            snapshot = read_service_snapshot(cache_root, request.session_id)
            self.assertEqual(snapshot.state, "cancelled")
            self.assertTrue(snapshot.service_done)
            self.assertTrue(runner.stop_requested)
            self.assertEqual(results, [])

    def test_service_delivers_receiver_rejection_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            request = create_receive_service_request(cache_root, "c" * 32)
            runner = _RejectableReceiveRunner()
            results: list[TransferNotification] = []
            runtime = TransferServiceRuntime(
                cache_root,
                runner_factory=lambda: runner,  # type: ignore[arg-type]
                notification_updater=lambda _message: None,
                result_notifier=results.append,
                sleep=lambda _seconds: time.sleep(0.001),
            )
            thread = threading.Thread(
                target=runtime.run,
                args=(request.session_id,),
            )
            thread.start()
            _wait_for_state(cache_root, request.session_id, "awaiting_decision")

            submit_service_command(
                cache_root,
                request.session_id,
                TransferServiceCommandName.REJECT,
            )
            thread.join(10)

            self.assertFalse(thread.is_alive())
            snapshot = read_service_snapshot(cache_root, request.session_id)
            self.assertEqual(snapshot.state, "rejected")
            self.assertTrue(snapshot.service_done)
            self.assertEqual(runner.calls, [None, b"n\n"])
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "Trasferimento rifiutato")


class AndroidTransferNotificationTests(unittest.TestCase):
    def test_only_active_notification_accepts_a_valid_cancel_session(self) -> None:
        session_id = "a" * 32
        active = build_transfer_notification(
            TransferServiceOperation.SEND,
            "sending_file",
            filename="example.bin",
            cancel_session_id=session_id,
        )
        terminal = build_transfer_notification(
            TransferServiceOperation.SEND,
            "completed",
            filename="example.bin",
            cancel_session_id=session_id,
        )

        self.assertEqual(active.cancel_session_id, session_id)
        self.assertIsNone(terminal.cancel_session_id)
        with self.assertRaisesRegex(ValueError, "Sessione di annullamento"):
            TransferNotification(
                title="Invio",
                text="In corso",
                cancel_session_id="not-a-session",
            )

    def test_active_progress_contains_useful_transfer_metrics(self) -> None:
        notification = build_transfer_notification(
            TransferServiceOperation.SEND,
            "sending_file",
            filename="example.bin",
            total_size=8 * 1024 * 1024,
            progress=TransferProgressSample(
                percent=25,
                transferred_bytes=2 * 1024 * 1024,
                total_bytes=8 * 1024 * 1024,
                speed_bps=1024 * 1024,
            ),
        )

        self.assertEqual(notification.title, "Invio: example.bin")
        self.assertEqual(notification.progress, 25)
        self.assertFalse(notification.indeterminate)
        self.assertIn("2.0 MiB / 8.0 MiB", notification.text)
        self.assertIn("1.0 MiB/s", notification.text)
        self.assertIn("6s rimanenti", notification.text)

    def test_waiting_and_verification_phases_use_the_right_bar_mode(self) -> None:
        waiting = build_transfer_notification(
            TransferServiceOperation.RECEIVE,
            "awaiting_decision",
            filename="example.bin",
        )
        verifying = build_transfer_notification(
            TransferServiceOperation.RECEIVE,
            "verifying",
            filename="example.bin",
        )

        self.assertIsNone(waiting.progress)
        self.assertFalse(waiting.indeterminate)
        self.assertIn("decisione", waiting.text)
        self.assertIsNone(verifying.progress)
        self.assertTrue(verifying.indeterminate)
        self.assertIn("SHA-256", verifying.text)

    def test_save_progress_is_reported_without_transport_details(self) -> None:
        notification = build_transfer_notification(
            TransferServiceOperation.RECEIVE,
            "saving",
            filename="example.bin",
            save_copied=512,
            save_total=1024,
        )

        self.assertEqual(notification.progress, 50)
        self.assertEqual(notification.text, "Salvataggio: 512 B / 1.0 KiB")

    def test_failure_result_does_not_expose_raw_error_details(self) -> None:
        notification = build_transfer_result_notification(
            TransferServiceOperation.RECEIVE,
            "failed",
            filename="private-name.txt",
        )

        self.assertIsNotNone(notification)
        assert notification is not None
        self.assertEqual(notification.title, "Trasferimento non riuscito")
        self.assertNotIn("private-name.txt", notification.text)
        self.assertNotIn("croc", notification.text.lower())
        self.assertEqual(
            notification.public_text,
            "Trasferimento MoonTransfer terminato",
        )

    def test_cancelled_transfer_does_not_leave_a_result_notification(self) -> None:
        self.assertIsNone(
            build_transfer_result_notification(
                TransferServiceOperation.SEND,
                "cancelled",
                filename="example.bin",
            )
        )

    def test_runtime_limits_progress_notification_frequency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            request = create_send_service_request(
                cache_root,
                _stage_file(cache_root),
            )
            now = [0.0]
            notifications: list[TransferNotification] = []
            runtime = TransferServiceRuntime(
                cache_root,
                notification_updater=notifications.append,
                result_notifier=lambda _notification: None,
                notification_clock=lambda: now[0],
            )
            runtime._initialize_notification(request)
            runtime._notify(force=True)
            runtime._set_notification_state(
                "sending_file",
                "Trasferimento del file in corso...",
            )

            for timestamp, percent in ((0.2, 10), (0.6, 20), (1.1, 30)):
                now[0] = timestamp
                with runtime._notification_lock:
                    runtime._notification_progress = TransferProgressSample(
                        percent=percent,
                        transferred_bytes=percent,
                        total_bytes=100,
                        speed_bps=10,
                    )
                runtime._notify()

            self.assertEqual(len(notifications), 2)
            self.assertEqual(notifications[-1].progress, 30)

    def test_runtime_reports_notification_errors_without_exposing_secrets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            code = "d" * 32
            request = create_receive_service_request(cache_root, code)

            def fail_update(_notification: TransferNotification) -> None:
                raise RuntimeError(f"builder failed for {code}")

            runtime = TransferServiceRuntime(
                cache_root,
                notification_updater=fail_update,
                result_notifier=lambda _notification: None,
            )
            runtime.request = request
            runtime._initialize_notification(request)
            output = io.StringIO()

            with redirect_stdout(output):
                runtime._notify(force=True)

            diagnostic = output.getvalue()
            self.assertIn("[notification] aggiornamento non riuscito", diagnostic)
            self.assertIn("<hidden>", diagnostic)
            self.assertNotIn(code, diagnostic)


if __name__ == "__main__":
    unittest.main()

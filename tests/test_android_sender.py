from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event


ROOT = Path(__file__).resolve().parents[1]
ANDROID_APP = ROOT / "android" / "app"
sys.path.insert(0, str(ANDROID_APP))

from moontransfer.cancellation import OperationCancelled  # noqa: E402
from moontransfer_android.sender import (  # noqa: E402
    AndroidSendCallbacks,
    AndroidSendController,
    AndroidSendState,
)
from moontransfer_android.storage import (  # noqa: E402
    StagedDocument,
    StagedSelection,
)
from moontransfer_android.transport import CrocProcessResult  # noqa: E402


class _FakeRunner:
    def __init__(
        self,
        *,
        metadata_returncode: int = 0,
        main_returncode: int = 0,
        main_lines: tuple[str, ...] = (),
        main_ready: bool = True,
        block: bool = False,
    ) -> None:
        self.metadata_returncode = metadata_returncode
        self.main_returncode = main_returncode
        self.main_lines = main_lines
        self.main_ready = main_ready
        self.block = block
        self.calls: list[dict[str, object]] = []
        self.metadata: dict[str, object] | None = None
        self.stop_requested = False
        self.metadata_finished = Event()

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
        process_guard: object = None,
    ) -> CrocProcessResult:
        is_metadata = str(args[-1]).endswith("moontransfer-metadata.json")
        self.calls.append(
            {
                "args": args,
                "config_dir": config_dir,
                "secret": secret,
                "workdir": workdir,
                "idle_timeout": idle_timeout,
            }
        )
        if is_metadata:
            try:
                self.metadata = json.loads(
                    Path(args[-1]).read_text(encoding="utf-8")
                )
                on_line("Code is: <hidden>")  # type: ignore[operator]
                if process_guard:
                    process_guard()  # type: ignore[operator]
                return CrocProcessResult(
                    returncode=self.metadata_returncode,
                    output_tail=(
                        "could not resolve the relay",
                        "https://getcroc.com/?code=<hidden>",
                    )
                    if self.metadata_returncode
                    else (),
                    stdout_tail=("could not resolve the relay",)
                    if self.metadata_returncode
                    else (),
                    stderr_tail=("https://getcroc.com/?code=<hidden>",)
                    if self.metadata_returncode
                    else (),
                )
            finally:
                self.metadata_finished.set()

        if self.main_ready:
            on_line("Code is: <hidden>")  # type: ignore[operator]
        else:
            return CrocProcessResult(
                returncode=self.main_returncode,
                output_tail=self.main_lines,
            )
        if self.block:
            while not cancel_requested():  # type: ignore[operator]
                time.sleep(0.01)
            raise OperationCancelled
        self.metadata_finished.wait(2)
        for line in self.main_lines:
            on_line(line)  # type: ignore[operator]
        return CrocProcessResult(
            returncode=self.main_returncode,
            output_tail=self.main_lines,
        )

    def request_stop(self) -> None:
        self.stop_requested = True


def _stage_file(root: Path, content: bytes = b"payload") -> StagedDocument:
    staging_dir = root / "staging" / "document"
    staging_dir.mkdir(parents=True)
    path = staging_dir / "example.bin"
    path.write_bytes(content)
    return StagedDocument(
        path=path,
        staging_dir=staging_dir,
        filename=path.name,
        size=len(content),
    )


class AndroidSendControllerTests(unittest.TestCase):
    def test_successful_send_uses_desktop_protocol_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = _stage_file(root)
            runner = _FakeRunner(
                main_lines=(
                    "Sending (->127.0.0.1:9009)",
                    "example.bin 100% | (7 B/7 B, 1 KB/s)",
                )
            )
            states: list[AndroidSendState] = []
            prepared: list[tuple[object, str]] = []
            progress: list[object] = []
            finished: list[tuple[AndroidSendState, str]] = []
            controller = AndroidSendController(
                metadata_runner=runner,  # type: ignore[arg-type]
                main_runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidSendCallbacks(
                    on_state=states.append,
                    on_prepared=lambda proposal, code: prepared.append(
                        (proposal, code)
                    ),
                    on_progress=progress.append,
                    on_finished=lambda state, message: finished.append(
                        (state, message)
                    ),
                ),
                idle_timeout=5,
            )

            controller.start(document)
            self.assertTrue(controller.wait(5))

            self.assertEqual(finished[-1][0], AndroidSendState.COMPLETED)
            self.assertIn(AndroidSendState.SENDING_METADATA, states)
            self.assertIn(AndroidSendState.AWAITING_DECISION, states)
            self.assertIn(AndroidSendState.SENDING_FILE, states)
            self.assertEqual(len(runner.calls), 2)
            self.assertFalse(
                str(runner.calls[0]["args"][-1]).endswith(
                    "moontransfer-metadata.json"
                )
            )
            self.assertTrue(
                str(runner.calls[1]["args"][-1]).endswith(
                    "moontransfer-metadata.json"
                )
            )
            self.assertNotEqual(
                runner.calls[0]["config_dir"],
                runner.calls[1]["config_dir"],
            )
            self.assertIsNotNone(runner.metadata)
            assert runner.metadata is not None
            self.assertEqual(runner.metadata["version"], 2)
            self.assertEqual(runner.metadata["roots"], ["example.bin"])
            self.assertEqual(runner.metadata["total_size"], 7)
            self.assertEqual(
                runner.metadata["main_code"],
                runner.calls[0]["secret"],
            )
            self.assertEqual(prepared[0][1], runner.calls[1]["secret"])
            self.assertNotEqual(
                runner.calls[0]["secret"],
                runner.calls[1]["secret"],
            )
            self.assertTrue(progress)
            self.assertEqual(progress[-1].percent, 100)
            self.assertFalse(document.staging_dir.exists())
            self.assertEqual(tuple((root / "sessions").iterdir()), ())

    def test_successful_send_publishes_multiple_staged_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_dir = root / "staging" / "first"
            second_dir = root / "staging" / "second"
            first_dir.mkdir(parents=True)
            second_dir.mkdir(parents=True)
            first_path = first_dir / "first.txt"
            second_path = second_dir / "second.txt"
            first_path.write_bytes(b"first")
            second_path.write_bytes(b"second")
            selection = StagedSelection(
                (
                    StagedDocument(
                        path=first_path,
                        staging_dir=first_dir,
                        filename=first_path.name,
                        size=first_path.stat().st_size,
                    ),
                    StagedDocument(
                        path=second_path,
                        staging_dir=second_dir,
                        filename=second_path.name,
                        size=second_path.stat().st_size,
                    ),
                )
            )
            runner = _FakeRunner()
            finished: list[AndroidSendState] = []
            controller = AndroidSendController(
                metadata_runner=runner,  # type: ignore[arg-type]
                main_runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidSendCallbacks(
                    on_finished=lambda state, _message: finished.append(state)
                ),
            )

            controller.start(selection)
            self.assertTrue(controller.wait(5))

            self.assertEqual(finished, [AndroidSendState.COMPLETED])
            assert runner.metadata is not None
            self.assertEqual(
                runner.metadata["roots"],
                ["first.txt", "second.txt"],
            )
            self.assertEqual(runner.metadata["file_count"], 2)
            self.assertEqual(runner.metadata["directory_count"], 0)
            self.assertEqual(runner.metadata["total_size"], 11)
            self.assertIn(str(first_path), runner.calls[0]["args"])
            self.assertIn(str(second_path), runner.calls[0]["args"])
            self.assertFalse(first_dir.exists())
            self.assertFalse(second_dir.exists())

    def test_receiver_rejection_is_reported_as_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = _FakeRunner(
                main_returncode=1,
                main_lines=("transfer rejected by recipient",),
            )
            finished: list[AndroidSendState] = []
            controller = AndroidSendController(
                metadata_runner=runner,  # type: ignore[arg-type]
                main_runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidSendCallbacks(
                    on_finished=lambda state, _message: finished.append(state)
                ),
            )

            controller.start(_stage_file(root))
            self.assertTrue(controller.wait(5))

            self.assertEqual(finished, [AndroidSendState.REJECTED])

    def test_main_preparation_failure_does_not_publish_metadata_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = _FakeRunner(main_returncode=2, main_ready=False)
            prepared: list[str] = []
            finished: list[AndroidSendState] = []
            controller = AndroidSendController(
                metadata_runner=runner,  # type: ignore[arg-type]
                main_runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidSendCallbacks(
                    on_prepared=lambda _proposal, code: prepared.append(code),
                    on_finished=lambda state, _message: finished.append(state),
                ),
            )

            controller.start(_stage_file(root))
            self.assertTrue(controller.wait(5))

            self.assertEqual(finished, [AndroidSendState.FAILED])
            self.assertEqual(prepared, [])
            self.assertEqual(len(runner.calls), 1)

    def test_main_exit_before_metadata_readiness_does_not_publish_code(
        self,
    ) -> None:
        class MainExitBeforeMetadataController(AndroidSendController):
            def _send_metadata(self, session) -> None:  # type: ignore[no-untyped-def]
                self._main_result = CrocProcessResult(
                    returncode=2,
                    output_tail=("main sender stopped",),
                )
                self._main_done.set()
                super()._send_metadata(session)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = _FakeRunner()
            prepared: list[str] = []
            finished: list[AndroidSendState] = []
            controller = MainExitBeforeMetadataController(
                metadata_runner=runner,  # type: ignore[arg-type]
                main_runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidSendCallbacks(
                    on_prepared=lambda _proposal, code: prepared.append(code),
                    on_finished=lambda state, _message: finished.append(state),
                ),
            )

            controller.start(_stage_file(root))
            self.assertTrue(controller.wait(5))

            self.assertEqual(finished, [AndroidSendState.FAILED])
            self.assertEqual(prepared, [])

    def test_metadata_failure_propagates_redacted_process_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = _FakeRunner(metadata_returncode=3)
            messages: list[str] = []
            states: list[AndroidSendState] = []
            controller = AndroidSendController(
                metadata_runner=runner,  # type: ignore[arg-type]
                main_runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidSendCallbacks(
                    on_finished=lambda state, message: (
                        states.append(state),
                        messages.append(message),
                    )
                ),
            )

            controller.start(_stage_file(root))
            self.assertTrue(controller.wait(5))

            self.assertEqual(states, [AndroidSendState.FAILED])
            self.assertIn("could not resolve the relay", messages[0])
            self.assertNotIn("getcroc.com", messages[0])

    def test_cancel_stops_active_runner_and_cleans_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = _stage_file(root)
            runner = _FakeRunner(block=True)
            finished = Event()
            states: list[AndroidSendState] = []
            controller = AndroidSendController(
                metadata_runner=runner,  # type: ignore[arg-type]
                main_runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidSendCallbacks(
                    on_finished=lambda state, _message: (
                        states.append(state),
                        finished.set(),
                    )
                ),
            )

            controller.start(document)
            deadline = time.monotonic() + 2
            while len(runner.calls) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            controller.cancel()

            self.assertTrue(finished.wait(2))
            self.assertTrue(controller.wait(2))
            self.assertTrue(runner.stop_requested)
            self.assertEqual(states, [AndroidSendState.CANCELLED])
            self.assertFalse(document.staging_dir.exists())


if __name__ == "__main__":
    unittest.main()

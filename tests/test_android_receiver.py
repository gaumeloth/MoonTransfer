from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ANDROID_APP = ROOT / "android" / "app"
sys.path.insert(0, str(ANDROID_APP))

from moontransfer.files import CONTROL_METADATA_NAME  # noqa: E402
from moontransfer.protocol import (  # noqa: E402
    PayloadEntry,
    create_payload_proposal,
    create_proposal,
    write_control_file,
)
from moontransfer_android.receiver import (  # noqa: E402
    AndroidReceiveCallbacks,
    AndroidReceiveController,
    AndroidReceiveState,
)
from moontransfer_android.transport import CrocProcessResult  # noqa: E402


class _FakeRunner:
    def __init__(
        self,
        proposal: object,
        *,
        content: bytes = b"payload",
        invalid_metadata: bool = False,
        metadata_returncode: int = 0,
        main_returncode: int = 0,
    ) -> None:
        self.proposal = proposal
        self.content = content
        self.invalid_metadata = invalid_metadata
        self.metadata_returncode = metadata_returncode
        self.main_returncode = main_returncode
        self.calls: list[dict[str, object]] = []
        self.stop_requested = False

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
        assert workdir is not None
        is_metadata = len(self.calls) == 0
        self.calls.append(
            {
                "args": args,
                "config_dir": config_dir,
                "secret": secret,
                "workdir": workdir,
                "idle_timeout": idle_timeout,
                "stdin_data": stdin_data,
            }
        )
        if is_metadata:
            metadata_path = workdir / CONTROL_METADATA_NAME
            if self.invalid_metadata:
                metadata_path.write_text("not-json", encoding="utf-8")
            else:
                write_control_file(metadata_path, self.proposal)
            if process_guard:
                process_guard()  # type: ignore[operator]
            return CrocProcessResult(
                returncode=self.metadata_returncode,
                output_tail=("metadata failed",)
                if self.metadata_returncode
                else (),
                stdout_tail=("metadata failed",)
                if self.metadata_returncode
                else (),
            )

        if stdin_data == b"y\n":
            filename = self.proposal.filename  # type: ignore[attr-defined]
            (workdir / filename).write_bytes(self.content)
            on_line(  # type: ignore[operator]
                f"{filename} 100% | ({len(self.content)} B/"
                f"{len(self.content)} B, 1 KB/s)"
            )
            if process_guard:
                process_guard()  # type: ignore[operator]
        return CrocProcessResult(
            returncode=self.main_returncode,
            output_tail=("main failed",) if self.main_returncode else (),
            stdout_tail=("main failed",) if self.main_returncode else (),
        )

    def request_stop(self) -> None:
        self.stop_requested = True


def _wait(event: Event, message: str) -> None:
    if not event.wait(3):
        raise AssertionError(message)


class AndroidReceiveControllerTests(unittest.TestCase):
    def test_accepts_verifies_and_saves_single_file(self) -> None:
        content = b"payload"
        proposal = create_proposal(
            filename="example.bin",
            size=len(content),
            sha256=(
                "239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5"
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = _FakeRunner(proposal, content=content)
            proposal_ready = Event()
            save_ready = Event()
            finished = Event()
            states: list[AndroidReceiveState] = []
            progress: list[object] = []
            saved: list[tuple[Path, object]] = []

            def save_file(
                source: Path,
                uri: object,
                *,
                cancel_requested: object,
                on_progress: object,
            ) -> int:
                destination = root / "saved.bin"
                shutil.copyfile(source, destination)
                on_progress(  # type: ignore[operator]
                    destination.stat().st_size,
                    destination.stat().st_size,
                )
                saved.append((destination, uri))
                return destination.stat().st_size

            controller = AndroidReceiveController(
                runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidReceiveCallbacks(
                    on_state=states.append,
                    on_proposal=lambda _proposal: proposal_ready.set(),
                    on_progress=progress.append,
                    on_save_ready=lambda _proposal: save_ready.set(),
                    on_finished=lambda _state, _message: finished.set(),
                ),
                main_receive_delay=0,
                save_file=save_file,
            )

            controller.start("a" * 32)
            _wait(proposal_ready, "proposal not received")
            controller.accept()
            _wait(save_ready, "verified file not ready to save")
            controller.save_to_uri("content://destination")
            _wait(finished, "receive controller did not finish")
            self.assertTrue(controller.wait(1))

            self.assertEqual(controller.state, AndroidReceiveState.COMPLETED)
            self.assertEqual(len(runner.calls), 2)
            self.assertEqual(runner.calls[0]["secret"], "a" * 32)
            self.assertEqual(runner.calls[1]["secret"], proposal.main_code)
            self.assertEqual(runner.calls[1]["stdin_data"], b"y\n")
            self.assertIn(AndroidReceiveState.VERIFYING, states)
            self.assertIn(AndroidReceiveState.AWAITING_SAVE, states)
            self.assertTrue(progress)
            self.assertEqual(saved[0][0].read_bytes(), content)
            self.assertEqual(saved[0][1], "content://destination")
            self.assertEqual(tuple((root / "sessions").iterdir()), ())

    def test_rejection_is_sent_through_main_croc_prompt(self) -> None:
        content = b"payload"
        proposal = create_proposal(
            filename="example.bin",
            size=len(content),
            sha256=(
                "239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5"
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = _FakeRunner(proposal, main_returncode=1)
            proposal_ready = Event()
            finished = Event()
            terminal: list[AndroidReceiveState] = []
            controller = AndroidReceiveController(
                runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidReceiveCallbacks(
                    on_proposal=lambda _proposal: proposal_ready.set(),
                    on_finished=lambda state, _message: (
                        terminal.append(state),
                        finished.set(),
                    ),
                ),
                main_receive_delay=0,
            )

            controller.start("b" * 32)
            _wait(proposal_ready, "proposal not received")
            controller.reject()
            _wait(finished, "rejection did not finish")

            self.assertEqual(terminal, [AndroidReceiveState.REJECTED])
            self.assertEqual(runner.calls[1]["stdin_data"], b"n\n")
            self.assertEqual(runner.calls[1]["secret"], proposal.main_code)
            self.assertEqual(tuple((root / "sessions").iterdir()), ())

    def test_multiple_files_are_rejected_automatically(self) -> None:
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
                    size=1,
                    sha256="b" * 64,
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = _FakeRunner(proposal)
            finished = Event()
            terminal: list[AndroidReceiveState] = []
            controller = AndroidReceiveController(
                runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidReceiveCallbacks(
                    on_finished=lambda state, _message: (
                        terminal.append(state),
                        finished.set(),
                    )
                ),
                main_receive_delay=0,
            )

            controller.start("c" * 32)
            _wait(finished, "unsupported transfer was not rejected")

            self.assertEqual(terminal, [AndroidReceiveState.REJECTED])
            self.assertEqual(runner.calls[1]["stdin_data"], b"n\n")

    def test_insufficient_private_space_rejects_after_user_accepts(self) -> None:
        proposal = create_proposal(
            filename="example.bin",
            size=7,
            sha256=(
                "239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5"
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            runner = _FakeRunner(proposal)
            proposal_ready = Event()
            finished = Event()
            terminal: list[AndroidReceiveState] = []
            controller = AndroidReceiveController(
                runner=runner,  # type: ignore[arg-type]
                sessions_parent=Path(tmp) / "sessions",
                callbacks=AndroidReceiveCallbacks(
                    on_proposal=lambda _proposal: proposal_ready.set(),
                    on_finished=lambda state, _message: (
                        terminal.append(state),
                        finished.set(),
                    ),
                ),
                main_receive_delay=0,
            )

            controller.start("1" * 32)
            _wait(proposal_ready, "proposal not received")
            with patch(
                "moontransfer_android.receiver.ensure_receive_capacity",
                side_effect=OSError("disk full"),
            ):
                controller.accept()
                _wait(finished, "capacity rejection did not finish")

            self.assertEqual(terminal, [AndroidReceiveState.REJECTED])
            self.assertEqual(runner.calls[1]["stdin_data"], b"n\n")

    def test_invalid_metadata_fails_and_cleans_session(self) -> None:
        proposal = create_proposal(
            filename="example.bin",
            size=0,
            sha256=(
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = _FakeRunner(proposal, invalid_metadata=True)
            finished = Event()
            result: list[tuple[AndroidReceiveState, str]] = []
            controller = AndroidReceiveController(
                runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidReceiveCallbacks(
                    on_finished=lambda state, message: (
                        result.append((state, message)),
                        finished.set(),
                    )
                ),
                main_receive_delay=0,
            )

            controller.start("d" * 32)
            _wait(finished, "invalid metadata did not fail")

            self.assertEqual(result[0][0], AndroidReceiveState.FAILED)
            self.assertIn("JSON", result[0][1])
            self.assertEqual(tuple((root / "sessions").iterdir()), ())

    def test_cancellation_while_waiting_for_decision_cleans_session(self) -> None:
        proposal = create_proposal(
            filename="empty.txt",
            size=0,
            sha256=(
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = _FakeRunner(proposal)
            proposal_ready = Event()
            finished = Event()
            terminal: list[AndroidReceiveState] = []
            controller = AndroidReceiveController(
                runner=runner,  # type: ignore[arg-type]
                sessions_parent=root / "sessions",
                callbacks=AndroidReceiveCallbacks(
                    on_proposal=lambda _proposal: proposal_ready.set(),
                    on_finished=lambda state, _message: (
                        terminal.append(state),
                        finished.set(),
                    ),
                ),
                main_receive_delay=0,
            )

            controller.start("e" * 32)
            _wait(proposal_ready, "proposal not received")
            controller.cancel()
            _wait(finished, "cancellation did not finish")

            self.assertEqual(terminal, [AndroidReceiveState.CANCELLED])
            self.assertTrue(runner.stop_requested)
            self.assertEqual(tuple((root / "sessions").iterdir()), ())

    def test_decision_timeout_rejects_transfer(self) -> None:
        proposal = create_proposal(
            filename="empty.txt",
            size=0,
            sha256=(
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            runner = _FakeRunner(proposal)
            finished = Event()
            result: list[tuple[AndroidReceiveState, str]] = []
            controller = AndroidReceiveController(
                runner=runner,  # type: ignore[arg-type]
                sessions_parent=Path(tmp) / "sessions",
                callbacks=AndroidReceiveCallbacks(
                    on_finished=lambda state, message: (
                        result.append((state, message)),
                        finished.set(),
                    )
                ),
                decision_timeout=0.05,
                main_receive_delay=0,
            )

            controller.start("f" * 32)
            _wait(finished, "decision timeout did not finish")

            self.assertEqual(result[0][0], AndroidReceiveState.REJECTED)
            self.assertIn("timeout", result[0][1])
            self.assertEqual(runner.calls[1]["stdin_data"], b"n\n")


if __name__ == "__main__":
    unittest.main()

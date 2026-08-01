from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from moontransfer.cancellation import OperationCancelled


ROOT = Path(__file__).resolve().parents[1]
ANDROID_APP = ROOT / "android" / "app"
sys.path.insert(0, str(ANDROID_APP))

from moontransfer_android import transport  # noqa: E402


class AndroidCrocResolutionTests(unittest.TestCase):
    def test_resolve_croc_executable_uses_native_library_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / transport.CROC_LIBRARY_NAME
            executable.touch(mode=0o755)

            self.assertEqual(
                transport.resolve_croc_executable(Path(tmp)),
                executable,
            )

    def test_resolve_croc_executable_rejects_missing_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(transport.CrocProbeError, "non trovato"):
                transport.resolve_croc_executable(Path(tmp))


class AndroidCrocProbeTests(unittest.TestCase):
    def test_probe_returns_version_and_isolates_configuration(self) -> None:
        process = Mock()
        process.returncode = 0
        process.communicate.return_value = ("croc version 10.7.0\n", "")
        process_factory = Mock(return_value=process)

        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "config"
            with patch.dict(os.environ, {"CROC_SECRET": "must-not-leak"}):
                result = transport.probe_croc(
                    config_dir,
                    executable=Path("/native/libcroc.so"),
                    process_factory=process_factory,
                )

        self.assertEqual(result.version, "10.7.0")
        command = process_factory.call_args.args[0]
        environment = process_factory.call_args.kwargs["env"]
        self.assertEqual(command, ["/native/libcroc.so", "--version"])
        self.assertNotIn("CROC_SECRET", environment)
        self.assertTrue(environment["HOME"].startswith(str(config_dir)))

    def test_probe_reports_nonzero_exit(self) -> None:
        process = Mock()
        process.returncode = 1
        process.communicate.return_value = ("", "startup failed")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(transport.CrocProbeError, "startup failed"):
                transport.probe_croc(
                    Path(tmp),
                    executable=Path("/native/libcroc.so"),
                    process_factory=Mock(return_value=process),
                )

    def test_probe_terminates_process_after_timeout(self) -> None:
        process = Mock()
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("croc", 0.01),
            ("", ""),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(transport.CrocProbeError, "timeout"):
                transport.probe_croc(
                    Path(tmp),
                    executable=Path("/native/libcroc.so"),
                    timeout=0.01,
                    process_factory=Mock(return_value=process),
                )

        process.terminate.assert_called_once_with()


class AndroidCrocProcessRunnerTests(unittest.TestCase):
    def test_runner_reads_carriage_return_records_and_redacts_secret(self) -> None:
        secret = "a" * 32
        lines: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = transport.CrocProcessRunner(Path(sys.executable))
            result = runner.run(
                [
                    "-c",
                    (
                        "import os,sys; "
                        "sys.stdout.write('first\\rCode is: ' + "
                        "os.environ['CROC_SECRET'] + '\\n'); "
                        "sys.stdout.flush()"
                    ),
                ],
                config_dir=root / "config",
                secret=secret,
                workdir=root,
                idle_timeout=2,
                cancel_requested=lambda: False,
                on_line=lines.append,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("first", lines)
        self.assertIn("Code is: <hidden>", lines)
        self.assertNotIn(secret, "\n".join(result.output_tail))

    def test_runner_reports_nonzero_exit_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = transport.CrocProcessRunner(Path(sys.executable))
            result = runner.run(
                ["-c", "import sys; print('failed'); raise SystemExit(7)"],
                config_dir=root / "config",
                secret="b" * 32,
                idle_timeout=2,
                cancel_requested=lambda: False,
            )

        self.assertEqual(result.returncode, 7)
        self.assertIn("failed", result.output_tail)
        self.assertIn("failed", result.stdout_tail)
        self.assertEqual(result.stderr_tail, ())

    def test_runner_preserves_stdout_and_stderr_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = transport.CrocProcessRunner(Path(sys.executable))
            result = runner.run(
                [
                    "-c",
                    (
                        "import sys; "
                        "print('actual failure'); "
                        "print('https://getcroc.com/?code=secret', file=sys.stderr); "
                        "raise SystemExit(1)"
                    ),
                ],
                config_dir=root / "config",
                secret="secret",
                idle_timeout=2,
                cancel_requested=lambda: False,
            )

        self.assertEqual(result.stdout_tail, ("actual failure",))
        self.assertEqual(
            result.stderr_tail,
            ("https://getcroc.com/?code=<hidden>",),
        )

    def test_runner_terminates_after_cancellation(self) -> None:
        cancelled = threading.Event()
        timer = threading.Timer(0.1, cancelled.set)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = transport.CrocProcessRunner(Path(sys.executable))
            timer.start()
            try:
                with self.assertRaises(OperationCancelled):
                    runner.run(
                        ["-c", "import time; time.sleep(30)"],
                        config_dir=root / "config",
                        secret="c" * 32,
                        idle_timeout=2,
                        cancel_requested=cancelled.is_set,
                    )
            finally:
                timer.cancel()

        self.assertFalse(runner.running)

    def test_runner_terminates_after_inactivity_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = transport.CrocProcessRunner(Path(sys.executable))
            with self.assertRaises(transport.CrocProcessTimeout):
                runner.run(
                    ["-c", "import time; time.sleep(30)"],
                    config_dir=root / "config",
                    secret="d" * 32,
                    idle_timeout=0.1,
                    cancel_requested=lambda: False,
                )

        self.assertFalse(runner.running)

    def test_runner_resets_inactivity_timeout_when_output_arrives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = transport.CrocProcessRunner(Path(sys.executable))
            result = runner.run(
                [
                    "-c",
                    (
                        "import sys,time; "
                        "[(print(index, flush=True), time.sleep(0.04)) "
                        "for index in range(6)]"
                    ),
                ],
                config_dir=root / "config",
                secret="e" * 32,
                idle_timeout=0.1,
                cancel_requested=lambda: False,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("5", result.output_tail)


if __name__ == "__main__":
    unittest.main()

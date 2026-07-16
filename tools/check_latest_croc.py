from __future__ import annotations

import argparse
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
for import_path in (PROJECT_ROOT, SRC_ROOT):
    import_path_text = str(import_path)
    if import_path_text not in sys.path:
        sys.path.insert(0, import_path_text)

from moontransfer import croc
from tools import fetch_croc


DEFAULT_TIMEOUT = 120


@dataclass(frozen=True)
class LatestCrocCheck:
    pinned_version: str
    latest_version: str

    @property
    def has_update(self) -> bool:
        return fetch_croc.compare_versions(self.latest_version, self.pinned_version) > 0


def checksum_asset_name(version: str) -> str:
    version = fetch_croc.normalize_version(version)
    return f"croc_v{version}_checksums.txt"


def checksum_download_url(version: str) -> str:
    version = fetch_croc.normalize_version(version)
    return (
        f"https://github.com/{fetch_croc.CROC_OWNER}/{fetch_croc.CROC_REPO}/"
        f"releases/download/v{version}/{checksum_asset_name(version)}"
    )


def read_latest_check(pyproject: Path) -> LatestCrocCheck:
    pinned_version, _ = fetch_croc.read_croc_config(pyproject)
    latest_version = fetch_croc.get_latest_croc_version()
    return LatestCrocCheck(
        pinned_version=pinned_version,
        latest_version=latest_version,
    )


def read_release_checksums(version: str) -> dict[str, str]:
    raw = fetch_croc.http_get(checksum_download_url(version))
    return fetch_croc.parse_checksum(raw.decode("utf-8", "replace"))


def fetch_release_binary(
    *,
    root: Path,
    version: str,
    asset: str,
    expected_hash: str,
) -> Path:
    cache = root / ".cache" / "croc-latest-check"
    archive = cache / asset
    url = fetch_croc.asset_download_url(version, asset)

    if archive.exists():
        try:
            fetch_croc.verify_archive(asset, archive, expected_hash)
            print(f"[cache] valid latest-check archive: {archive.name}")
            return archive
        except Exception as exc:
            print(f"[warn] invalid latest-check archive ({exc}); downloading again")

    print(f"[fetch] {url}")
    fetch_croc.download_atomic(url, archive)
    fetch_croc.verify_archive(asset, archive, expected_hash)
    print("[ok] checksum verified")
    return archive


def expected_release_hash(asset: str, checksums: dict[str, str]) -> str:
    expected = checksums.get(asset)
    if not expected:
        raise RuntimeError(f"Latest croc checksum file does not list {asset}")
    return fetch_croc.normalize_hash(expected)


def extracted_binary_path(root: Path, asset: str, archive: Path) -> Path:
    extract_dir = root / ".cache" / "croc-latest-check" / "extract"
    fetch_croc.extract_archive(asset, archive, extract_dir)

    exe = "croc.exe" if os.name == "nt" else "croc"
    found = next(extract_dir.rglob(exe), None)
    if not found:
        raise RuntimeError("croc binary not found in latest release archive")

    if os.name != "nt":
        found.chmod(found.stat().st_mode | 0o111)

    return found


def command_output(args: list[str], *, cwd: Path | None = None, timeout: int = 30) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(args)}\n"
            f"{output}"
        )
    return output


def smoke_command_args(binary: Path) -> list[list[str]]:
    program = str(binary)
    return [
        [program, "--version"],
        [
            program,
            "--classic=false",
            "--ignore-stdin",
            "--disable-clipboard",
            "send",
            "--no-local",
            "--help",
        ],
        [
            program,
            "--classic=false",
            "--ignore-stdin",
            "--yes",
            "--overwrite",
            "--help",
        ],
    ]


def run_smoke_tests(binary: Path, version: str) -> None:
    print(f"[smoke] testing {binary}")

    version_command, send_help_command, receive_help_command = smoke_command_args(binary)

    version_output = command_output(version_command)
    if f"v{fetch_croc.normalize_version(version)}" not in version_output:
        raise RuntimeError(
            f"Unexpected croc version output for {binary}:\n{version_output}"
        )

    send_help = command_output(send_help_command)
    if "--no-local" not in send_help:
        raise RuntimeError("Latest croc send help does not mention --no-local")

    receive_help = command_output(receive_help_command)
    if "--overwrite" not in receive_help:
        raise RuntimeError("Latest croc help does not mention --overwrite")

    preview = croc.build_secret_preview(str(binary), croc.build_receive_args())
    if "CROC_SECRET=<hidden>" not in preview:
        raise RuntimeError("MoonTransfer receive preview no longer hides CROC_SECRET")

    print("[ok] smoke tests passed")


def _enqueue_output(
    stream,
    lines: queue.Queue[str],
    sink: list[str],
) -> None:
    try:
        for line in iter(stream.readline, ""):
            sink.append(line)
            lines.put(line.rstrip("\r\n"))
    finally:
        stream.close()


def run_transfer_test(binary: Path, *, timeout: int = DEFAULT_TIMEOUT) -> None:
    print("[transfer] running end-to-end transfer test with latest croc")

    with tempfile.TemporaryDirectory(prefix="moontransfer-croc-latest-") as tmp:
        base = Path(tmp)
        source_dir = base / "source"
        dest_dir = base / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        source_file = source_dir / "moontransfer-latest-croc-test.txt"
        source_file.write_text("moontransfer latest croc transfer test\n", encoding="utf-8")

        sender_output: list[str] = []
        sender_lines: queue.Queue[str] = queue.Queue()
        sender = subprocess.Popen(
            [str(binary), *croc.build_send_args(source_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(source_dir),
            env={
                **{
                    key: value
                    for key, value in os.environ.items()
                    if key != croc.CROC_SECRET_ENV
                },
                **croc.build_process_environment(base / "sender-croc-config"),
            },
        )

        assert sender.stdout is not None
        sender_reader = threading.Thread(
            target=_enqueue_output,
            args=(sender.stdout, sender_lines, sender_output),
            daemon=True,
        )
        sender_reader.start()

        receiver: subprocess.Popen[str] | None = None
        receiver_output: list[str] = []

        try:
            deadline = time.monotonic() + timeout
            code = None
            while time.monotonic() < deadline:
                try:
                    line = sender_lines.get(timeout=0.2)
                except queue.Empty:
                    if sender.poll() is not None:
                        break
                    continue

                parsed = croc.parse_send_code(line)
                if parsed:
                    code = parsed
                    break

            if not code:
                raise RuntimeError(
                    "sender did not produce a croc code\n"
                    + "".join(sender_output[-40:])
                )

            receiver_env = os.environ.copy()
            receiver_env.update(
                croc.build_process_environment(
                    base / "receiver-croc-config",
                    secret=code,
                )
            )
            receiver = subprocess.Popen(
                [str(binary), *croc.build_receive_args()],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(dest_dir),
                env=receiver_env,
            )

            assert receiver.stdout is not None
            receiver_thread = threading.Thread(
                target=_enqueue_output,
                args=(receiver.stdout, queue.Queue(), receiver_output),
                daemon=True,
            )
            receiver_thread.start()

            receiver.wait(timeout=timeout)
            sender.wait(timeout=timeout)

            received_file = dest_dir / source_file.name
            if not received_file.is_file():
                raise RuntimeError(
                    "received file was not created\n"
                    f"sender output:\n{''.join(sender_output[-80:])}\n"
                    f"receiver output:\n{''.join(receiver_output[-80:])}"
                )

            if received_file.read_text(encoding="utf-8") != source_file.read_text(encoding="utf-8"):
                raise RuntimeError("received file content does not match source content")

        finally:
            for proc in (receiver, sender):
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()

    print("[ok] transfer test passed")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check and test the latest upstream croc release."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="test the latest release even if it is not newer than the pinned version",
    )
    parser.add_argument(
        "--transfer",
        action="store_true",
        help="also run an end-to-end transfer test using the latest croc binary",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="timeout in seconds for the optional transfer test",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    root = PROJECT_ROOT

    check = read_latest_check(root / "pyproject.toml")
    print(f"[pinned] croc v{check.pinned_version}")
    print(f"[latest] croc v{check.latest_version}")

    if not check.has_update and not args.force:
        print("[ok] pinned croc is up to date")
        return

    if check.has_update:
        print(f"[update] croc v{check.latest_version} is newer than pinned v{check.pinned_version}")
    else:
        print("[force] testing latest even though it is not newer than pinned")

    asset = fetch_croc.pick_asset(check.latest_version)
    checksums = read_release_checksums(check.latest_version)
    expected_hash = expected_release_hash(asset, checksums)
    archive = fetch_release_binary(
        root=root,
        version=check.latest_version,
        asset=asset,
        expected_hash=expected_hash,
    )
    binary = extracted_binary_path(root, asset, archive)

    run_smoke_tests(binary, check.latest_version)

    if args.transfer:
        run_transfer_test(binary, timeout=args.timeout)

    print("[done] latest croc check passed")
    print(
        "[next] if the result is acceptable, update "
        "[tool.moontransfer.croc] in pyproject.toml and commit the new hashes"
    )


if __name__ == "__main__":
    main()

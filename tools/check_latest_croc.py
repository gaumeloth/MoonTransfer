from __future__ import annotations

import argparse
import os
import queue
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
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
COMPATIBILITY_ENV_KEYS = frozenset(
    {
        "ALL_PROXY",
        "COMSPEC",
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "NO_PROXY",
        "NUMBER_OF_PROCESSORS",
        "PATHEXT",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TZ",
        "WINDIR",
    }
)


@dataclass(frozen=True)
class LatestCrocCheck:
    pinned_version: str
    latest_version: str

    @property
    def has_update(self) -> bool:
        return fetch_croc.compare_versions(self.latest_version, self.pinned_version) > 0


@dataclass(frozen=True)
class CrocBinary:
    version: str
    path: Path


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


def extracted_binary_path(
    root: Path,
    version: str,
    asset: str,
    archive: Path,
) -> Path:
    version = fetch_croc.normalize_version(version)
    extract_dir = root / ".cache" / "croc-latest-check" / "extract" / version
    fetch_croc.extract_archive(asset, archive, extract_dir)

    exe = "croc.exe" if os.name == "nt" else "croc"
    found = next(extract_dir.rglob(exe), None)
    if not found:
        raise RuntimeError("croc binary not found in latest release archive")

    if os.name != "nt":
        found.chmod(found.stat().st_mode | 0o111)

    return found


def fetch_verified_binary(*, root: Path, version: str) -> CrocBinary:
    version = fetch_croc.normalize_version(version)
    asset = fetch_croc.pick_asset(version)
    checksums = read_release_checksums(version)
    expected_hash = expected_release_hash(asset, checksums)
    archive = fetch_release_binary(
        root=root,
        version=version,
        asset=asset,
        expected_hash=expected_hash,
    )
    return CrocBinary(
        version=version,
        path=extracted_binary_path(root, version, asset, archive),
    )


def compatibility_process_environment(
    config_dir: Path,
    *,
    secret: str | None = None,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = os.environ if base_env is None else base_env
    environment = {
        key: value
        for key, value in source.items()
        if key.upper() in COMPATIBILITY_ENV_KEYS
    }
    environment.update(
        croc.build_process_environment(
            config_dir,
            secret=secret,
        )
    )
    return environment


def command_output(
    args: list[str],
    *,
    env: Mapping[str, str],
    cwd: Path | None = None,
    timeout: int = 30,
) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=dict(env),
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

    with tempfile.TemporaryDirectory(prefix="moontransfer-croc-smoke-") as tmp:
        environment = compatibility_process_environment(Path(tmp) / "croc-config")

        version_output = command_output(version_command, env=environment)
        reported_version = croc.parse_version_output(version_output)
        expected_version = fetch_croc.normalize_version(version)
        if reported_version != expected_version:
            raise RuntimeError(
                f"Unexpected croc version for {binary}: "
                f"expected {expected_version}, got "
                f"{reported_version or 'unknown'}\n{version_output}"
            )

        send_help = command_output(send_help_command, env=environment)
        if "--no-local" not in send_help:
            raise RuntimeError("Latest croc send help does not mention --no-local")

        receive_help = command_output(receive_help_command, env=environment)
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


def run_transfer_test(
    sender_binary: CrocBinary,
    *,
    receiver_binary: CrocBinary | None = None,
    prompt_response: bool | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> None:
    receiver_binary = receiver_binary or sender_binary
    if prompt_response is None:
        mode = "automatic receive"
    elif prompt_response:
        mode = "prompt acceptance"
    else:
        mode = "prompt rejection"
    print(
        f"[transfer] {mode}: "
        f"sender=v{sender_binary.version}, receiver=v{receiver_binary.version}"
    )

    with tempfile.TemporaryDirectory(prefix="moontransfer-croc-latest-") as tmp:
        base = Path(tmp)
        source_dir = base / "source"
        dest_dir = base / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        source_file = source_dir / "moontransfer-latest-croc-test.txt"
        source_file.write_text(
            "moontransfer latest croc transfer test\n",
            encoding="utf-8",
        )
        source_folder = source_dir / "moontransfer-folder"
        nested_folder = source_folder / "nested"
        empty_folder = source_folder / "empty"
        nested_folder.mkdir(parents=True)
        empty_folder.mkdir()
        (nested_folder / "dati-città.txt").write_text(
            "nested moontransfer compatibility test\n",
            encoding="utf-8",
        )

        sender_output: list[str] = []
        sender_lines: queue.Queue[str] = queue.Queue()
        expected_code = secrets.token_hex(16)
        sender = subprocess.Popen(
            [
                str(sender_binary.path),
                *croc.build_send_args((source_file, source_folder)),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(source_dir),
            env=compatibility_process_environment(
                base / "sender-croc-config",
                secret=expected_code,
            ),
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
                    if parsed != expected_code:
                        raise RuntimeError(
                            "sender reported a different custom transfer code"
                        )
                    code = parsed
                    break

            if not code:
                raise RuntimeError(
                    "sender did not produce a croc code\n"
                    + "".join(sender_output[-40:])
                )

            receiver_env = compatibility_process_environment(
                base / "receiver-croc-config",
                secret=code,
            )
            receive_args = (
                croc.build_receive_args()
                if prompt_response is None
                else croc.build_prompted_receive_args()
            )
            receiver = subprocess.Popen(
                [str(receiver_binary.path), *receive_args],
                stdin=(
                    subprocess.PIPE
                    if prompt_response is not None
                    else subprocess.DEVNULL
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(dest_dir),
                env=receiver_env,
            )

            if prompt_response is not None:
                assert receiver.stdin is not None
                receiver.stdin.write("y\n" if prompt_response else "n\n")
                receiver.stdin.flush()
                receiver.stdin.close()

            assert receiver.stdout is not None
            receiver_thread = threading.Thread(
                target=_enqueue_output,
                args=(receiver.stdout, queue.Queue(), receiver_output),
                daemon=True,
            )
            receiver_thread.start()

            receiver.wait(timeout=timeout)
            sender.wait(timeout=timeout)
            receiver_thread.join(timeout=2)
            sender_reader.join(timeout=2)

            if prompt_response is False:
                received_entries = tuple(dest_dir.iterdir())
                if received_entries:
                    raise RuntimeError(
                        "prompt rejection created destination content\n"
                        f"sender output:\n{''.join(sender_output[-80:])}\n"
                        f"receiver output:\n{''.join(receiver_output[-80:])}"
                    )
                print(f"[ok] {mode} test passed")
                return

            if sender.returncode != 0 or receiver.returncode != 0:
                raise RuntimeError(
                    "accepted transfer process failed\n"
                    f"sender exit code: {sender.returncode}\n"
                    f"receiver exit code: {receiver.returncode}\n"
                    f"sender output:\n{''.join(sender_output[-80:])}\n"
                    f"receiver output:\n{''.join(receiver_output[-80:])}"
                )

            received_file = dest_dir / source_file.name
            received_nested = (
                dest_dir
                / source_folder.name
                / "nested"
                / "dati-città.txt"
            )
            received_empty = dest_dir / source_folder.name / "empty"
            if (
                not received_file.is_file()
                or not received_nested.is_file()
                or not received_empty.is_dir()
            ):
                raise RuntimeError(
                    "received multi-item payload is incomplete\n"
                    f"sender output:\n{''.join(sender_output[-80:])}\n"
                    f"receiver output:\n{''.join(receiver_output[-80:])}"
                )

            expected_files = (
                (source_file, received_file),
                (nested_folder / "dati-città.txt", received_nested),
            )
            for original, received in expected_files:
                if received.read_bytes() != original.read_bytes():
                    raise RuntimeError(
                        f"received content does not match source: {original.name}"
                    )

        finally:
            for proc in (receiver, sender):
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)

    print(f"[ok] {mode} test passed")


def transfer_pairs(
    latest: CrocBinary,
    compatible: CrocBinary | None = None,
) -> tuple[tuple[CrocBinary, CrocBinary], ...]:
    pairs = [(latest, latest)]
    if compatible is not None and compatible.version != latest.version:
        pairs.extend(((compatible, latest), (latest, compatible)))
    return tuple(pairs)


def run_transfer_matrix(
    latest: CrocBinary,
    *,
    compatible: CrocBinary | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> None:
    failures: list[str] = []
    for sender, receiver in transfer_pairs(latest, compatible):
        try:
            run_transfer_test(
                sender,
                receiver_binary=receiver,
                timeout=timeout,
            )
        except RuntimeError as exc:
            failures.append(
                f"sender v{sender.version} -> receiver v{receiver.version}: {exc}"
            )
            print(f"[fail] {failures[-1]}")
            continue

        for prompt_response in (True, False):
            try:
                run_transfer_test(
                    sender,
                    receiver_binary=receiver,
                    prompt_response=prompt_response,
                    timeout=timeout,
                )
            except RuntimeError as exc:
                failures.append(
                    f"sender v{sender.version} -> receiver v{receiver.version}: {exc}"
                )
                print(f"[fail] {failures[-1]}")

    if failures:
        raise RuntimeError(
            f"croc transfer matrix failed in {len(failures)} case(s)\n\n"
            + "\n\n".join(failures)
        )


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
        help=(
            "also test automatic receive plus prompted acceptance and rejection "
            "using the latest croc binary"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="timeout in seconds for the optional transfer test",
    )
    parser.add_argument(
        "--compat-version",
        help=(
            "with --transfer, also test both transfer directions between the "
            "latest release and this croc version"
        ),
    )
    args = parser.parse_args(argv)
    if args.compat_version and not args.transfer:
        parser.error("--compat-version requires --transfer")
    return args


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

    latest_binary = fetch_verified_binary(
        root=root,
        version=check.latest_version,
    )

    run_smoke_tests(latest_binary.path, latest_binary.version)

    if args.transfer:
        compatible_binary = None
        if args.compat_version:
            compatible_binary = fetch_verified_binary(
                root=root,
                version=args.compat_version,
            )
            run_smoke_tests(
                compatible_binary.path,
                compatible_binary.version,
            )
        run_transfer_matrix(
            latest_binary,
            compatible=compatible_binary,
            timeout=args.timeout,
        )

    print("[done] latest croc check passed")
    if check.has_update:
        print(
            "[next] if the result is acceptable, update "
            "[tool.moontransfer.croc] in pyproject.toml and commit the new hashes"
        )
    else:
        print("[ok] pinned croc release validated")


if __name__ == "__main__":
    main()

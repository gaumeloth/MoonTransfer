from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tarfile
import time
import tomllib
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen


CROC_OWNER = "schollz"
CROC_REPO = "croc"
USER_AGENT = "moontransfer-build/1.0"


def _is_within_dir(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


def safe_extract_tar(tar: tarfile.TarFile, dst: Path) -> None:
    dst = dst.resolve()
    for member in tar.getmembers():
        out = dst / member.name
        if not _is_within_dir(dst, out):
            raise RuntimeError(f"Path traversal in tar archive: {member.name}")
        if member.issym() or member.islnk():
            raise RuntimeError(f"Links are not supported in tar archive: {member.name}")
    tar.extractall(dst)


def safe_extract_zip(zip_file: zipfile.ZipFile, dst: Path) -> None:
    dst = dst.resolve()
    for name in zip_file.namelist():
        out = dst / name
        if not _is_within_dir(dst, out):
            raise RuntimeError(f"Path traversal in zip archive: {name}")
    zip_file.extractall(dst)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_hash(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("sha256:"):
        value = value.removeprefix("sha256:")

    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"Invalid SHA-256 hash: {value!r}")

    return value


def parse_checksum(text: str) -> dict[str, str]:
    hashes = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            hashes[parts[1]] = normalize_hash(parts[0])
    return hashes


def verify_archive(asset: str, archive: Path, expected_hash: str) -> None:
    expected = normalize_hash(expected_hash)
    got = sha256_file(archive)
    if got != expected:
        raise RuntimeError(
            f"SHA256 mismatch for {asset}\n"
            f" expected={expected}\n"
            f" got     ={got}"
        )


def http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> bytes:
    final_headers = {"User-Agent": USER_AGENT}
    if headers:
        final_headers.update(headers)

    request = Request(url, headers=final_headers)
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def github_api_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


def normalize_version(version: str) -> str:
    version = version.strip()
    if version.startswith("v"):
        version = version[1:]
    return version


def parse_version(version: str) -> tuple[int, int, int]:
    version = normalize_version(version)
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"Unsupported version format: {version!r}")

    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def compare_versions(left: str, right: str) -> int:
    left_tuple = parse_version(left)
    right_tuple = parse_version(right)

    if left_tuple < right_tuple:
        return -1
    if left_tuple > right_tuple:
        return 1
    return 0


def read_installed_version(version_file: Path) -> str | None:
    if not version_file.exists():
        return None

    value = version_file.read_text(encoding="utf-8").strip()
    if not value:
        return None

    return normalize_version(value)


def read_croc_config(pyproject: Path) -> tuple[str, dict[str, str]]:
    with pyproject.open("rb") as file:
        data = tomllib.load(file)

    try:
        config = data["tool"]["moontransfer"]["croc"]
    except KeyError as exc:
        raise RuntimeError(
            "Missing [tool.moontransfer.croc] configuration in pyproject.toml"
        ) from exc

    version = config.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("Missing croc version in [tool.moontransfer.croc]")

    raw_hashes = config.get("hashes")
    if not isinstance(raw_hashes, dict) or not raw_hashes:
        raise RuntimeError("Missing croc asset hashes in [tool.moontransfer.croc.hashes]")

    hashes = {}
    for asset, value in raw_hashes.items():
        if not isinstance(asset, str) or not isinstance(value, str):
            raise RuntimeError("croc asset hashes must be string-to-string values")
        hashes[asset] = normalize_hash(value)

    return normalize_version(version), hashes


def get_latest_croc_version() -> str:
    api_url = (
        f"https://api.github.com/repos/"
        f"{CROC_OWNER}/{CROC_REPO}/releases/latest"
    )

    raw = http_get(api_url, headers=github_api_headers())
    data = json.loads(raw.decode("utf-8"))

    tag_name = data.get("tag_name")
    if not tag_name:
        raise RuntimeError("GitHub API response is missing tag_name")

    return normalize_version(tag_name)


def download_atomic(
    url: str,
    dest: Path,
    *,
    timeout: int = 60,
    chunk_size: int = 1024 * 1024,
    retries: int = 3,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")

    if tmp.exists():
        tmp.unlink()

    for attempt in range(1, retries + 1):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:
                total = response.headers.get("Content-Length")
                total_int = int(total) if total and total.isdigit() else None

                downloaded = 0
                last_print = 0.0

                with tmp.open("wb") as file:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break

                        file.write(chunk)
                        downloaded += len(chunk)

                        if sys.stdout.isatty():
                            now = time.time()
                            if now - last_print >= 0.1:
                                if total_int:
                                    pct = downloaded * 100 // total_int
                                    print(
                                        f"\r[dl] {dest.name} {pct:3d}% "
                                        f"({downloaded}/{total_int} bytes)",
                                        end="",
                                        flush=True,
                                    )
                                else:
                                    print(
                                        f"\r[dl] {dest.name} ({downloaded} bytes)",
                                        end="",
                                        flush=True,
                                    )
                                last_print = now

                if sys.stdout.isatty():
                    print()

            tmp.replace(dest)
            return

        except Exception as exc:
            if tmp.exists():
                tmp.unlink()

            if attempt == retries:
                raise RuntimeError(
                    f"Download failed after {retries} attempts: {url}\n"
                    f"Last error: {exc}"
                ) from exc

            time.sleep(0.5 * attempt)


def _is_arm64(machine: str) -> bool:
    return machine in {"arm64", "aarch64"}


def _is_x86_64(machine: str) -> bool:
    return machine in {"x86_64", "amd64"}


def pick_asset(
    version: str,
    *,
    system: str | None = None,
    machine: str | None = None,
) -> str:
    version = normalize_version(version)
    sysname = (system or platform.system()).lower()
    mach = (machine or platform.machine()).lower()

    if sysname == "windows":
        if _is_arm64(mach):
            return f"croc_v{version}_Windows-ARM64.zip"
        if _is_x86_64(mach):
            return f"croc_v{version}_Windows-64bit.zip"

    if sysname == "darwin":
        if _is_arm64(mach):
            return f"croc_v{version}_macOS-ARM64.tar.gz"
        if _is_x86_64(mach):
            return f"croc_v{version}_macOS-64bit.tar.gz"

    if sysname == "linux":
        if _is_arm64(mach):
            return f"croc_v{version}_Linux-ARM64.tar.gz"
        if _is_x86_64(mach):
            return f"croc_v{version}_Linux-64bit.tar.gz"

    raise RuntimeError(f"Unsupported platform: {platform.system()} {platform.machine()}")


def asset_download_url(version: str, asset: str) -> str:
    version = normalize_version(version)
    return (
        f"https://github.com/{CROC_OWNER}/{CROC_REPO}/releases/download/"
        f"v{version}/{asset}"
    )


def expected_hash_for_asset(asset: str, hashes: dict[str, str]) -> str:
    expected = hashes.get(asset)
    if not expected:
        raise RuntimeError(
            f"Missing pinned SHA-256 hash for {asset}. "
            "Add it to [tool.moontransfer.croc.hashes]."
        )
    return normalize_hash(expected)


def extract_archive(asset: str, archive: Path, extract_dir: Path) -> None:
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir()

    if asset.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zip_file:
            safe_extract_zip(zip_file, extract_dir)
    else:
        with tarfile.open(archive, "r:gz") as tar:
            safe_extract_tar(tar, extract_dir)


def install_croc_binary(extract_dir: Path, dest: Path, exe: str) -> None:
    found = next(extract_dir.rglob(exe), None)
    if not found:
        raise RuntimeError("croc binary not found in extracted archive")

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(found, dest)
    if os.name != "nt":
        dest.chmod(dest.stat().st_mode | 0o111)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch the pinned croc binary.")
    parser.add_argument(
        "--version",
        help="fetch a specific croc version that has pinned hashes in pyproject.toml",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="print the latest upstream croc version and exit",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    root = Path(__file__).resolve().parent.parent

    if args.latest:
        print(get_latest_croc_version())
        return

    configured_version, hashes = read_croc_config(root / "pyproject.toml")
    target_version = normalize_version(args.version or configured_version)

    outdir = root / "third_party" / "croc"
    exe = "croc.exe" if os.name == "nt" else "croc"
    dest = outdir / exe
    version_file = outdir / "VERSION"
    installed_version = read_installed_version(version_file)

    asset = pick_asset(target_version)
    expected_hash = expected_hash_for_asset(asset, hashes)

    if dest.exists() and installed_version == target_version:
        print(f"[ok] croc v{installed_version} already installed: {dest}")
        return

    if installed_version:
        print(f"[local] croc installed: v{installed_version}")
    else:
        print("[local] croc is not installed")

    print(f"[target] croc version: v{target_version}")

    cache = root / ".cache"
    archive = cache / asset
    url = asset_download_url(target_version, asset)

    if archive.exists():
        try:
            verify_archive(asset, archive, expected_hash)
            print(f"[cache] valid archive: {archive.name}")
        except Exception as exc:
            print(f"[warn] invalid cached archive ({exc}); downloading again")
            download_atomic(url, archive)
            verify_archive(asset, archive, expected_hash)
            print("[ok] checksum verified")
    else:
        print(f"[fetch] {url}")
        download_atomic(url, archive)
        verify_archive(asset, archive, expected_hash)
        print("[ok] checksum verified")

    extract_dir = cache / "croc_extract"
    extract_archive(asset, archive, extract_dir)
    install_croc_binary(extract_dir, dest, exe)

    version_file.write_text(target_version + "\n", encoding="utf-8")
    print(f"[ok] croc ready: {dest}")
    print(f"[ok] version marker written: {version_file}")


if __name__ == "__main__":
    main()

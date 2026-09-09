"""Validate the complete desktop + Android asset set before creating a draft."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import tempfile

from tools.build_metadata import read_project_settings


ROOT = Path(__file__).resolve().parents[1]
PRERELEASE_TAG = re.compile(r"v([0-9]+\.[0-9]+\.[0-9]+-(?:alpha|beta|rc)\.[0-9]+)")
ASSET_SUFFIXES = (
    "linux-x86_64.tar.gz",
    "windows-x86_64.zip",
    "macos-x86_64.tar.gz",
    "macos-arm64.tar.gz",
    "android-arm64.apk",
)


def version_from_tag(tag: str, *, project_version: str) -> str:
    match = PRERELEASE_TAG.fullmatch(tag)
    if match is None:
        raise ValueError("Expected vX.Y.Z-alpha.N, vX.Y.Z-beta.N or vX.Y.Z-rc.N.")
    version = match.group(1)
    if version.split("-", 1)[0] != project_version:
        raise ValueError("Pre-release tag does not match the project's numeric version.")
    return version


def write_checksums(directory: Path, *, tag: str, project_version: str) -> Path:
    version = version_from_tag(tag, project_version=project_version)
    expected = {f"MoonTransfer-{version}-{suffix}" for suffix in ASSET_SUFFIXES}
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Expected a regular release asset directory.")
    actual = {entry.name for entry in directory.iterdir()} - {"SHA256SUMS"}
    if actual != expected:
        raise ValueError(
            f"Incomplete or unexpected release assets; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )
    lines = []
    for name in sorted(expected):
        path = directory / name
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Empty, non-file or symbolic release asset: {name}")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        lines.append(f"{digest}  {name}\n")
    destination = directory / "SHA256SUMS"
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError("Unsafe checksum destination.")
    with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=directory, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.writelines(lines)
            stream.close()
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-tag")
    validate.add_argument("tag")
    checksums = commands.add_parser("checksums")
    checksums.add_argument("--tag", required=True)
    checksums.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        project_version, _ = read_project_settings(ROOT / "pyproject.toml")
        if args.command == "validate-tag":
            print(version_from_tag(args.tag, project_version=project_version))
        else:
            print(write_checksums(args.directory, tag=args.tag, project_version=project_version))
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

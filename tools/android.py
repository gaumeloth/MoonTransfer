from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from tools.prepare_android import ROOT, prepare_android_source


ANDROID_DIR = ROOT / "android"
BUILD_SPEC = ANDROID_DIR / "buildozer.spec"
EXPECTED_PYTHON = (3, 13)
COMMON_BUILD_COMMANDS = (
    "git",
    "zip",
    "unzip",
    "make",
    "cmake",
    "javac",
    "cargo",
    "rustc",
)
LINUX_BUILD_COMMANDS = (
    "autoconf",
    "automake",
    "autopoint",
    "libtool",
    "pkg-config",
    "gcc",
    "g++",
)
MACOS_BUILD_COMMANDS = (
    "autoconf",
    "automake",
    "libtool",
    "pkg-config",
    "clang",
)


def required_build_commands(system: str) -> tuple[str, ...]:
    platform_commands = {
        "Linux": LINUX_BUILD_COMMANDS,
        "Darwin": MACOS_BUILD_COMMANDS,
    }.get(system, ())
    return COMMON_BUILD_COMMANDS + platform_commands


def find_missing_commands(
    commands: Sequence[str],
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> tuple[str, ...]:
    return tuple(command for command in commands if which(command) is None)


def find_missing_python_modules(
    modules: Sequence[str],
    *,
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
) -> tuple[str, ...]:
    return tuple(module for module in modules if find_spec(module) is None)


def javac_major_version() -> int | None:
    javac = shutil.which("javac")
    if javac is None:
        return None
    result = subprocess.run(
        [javac, "-version"],
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"javac\s+(\d+)", result.stdout + result.stderr)
    return int(match.group(1)) if match else None


def build_environment_issues() -> tuple[str, ...]:
    issues: list[str] = []
    system = platform.system()
    if system not in {"Linux", "Darwin"}:
        issues.append("Android builds require Linux or macOS.")

    if sys.version_info[:2] != EXPECTED_PYTHON:
        issues.append(
            "The Android environment must use Python 3.13 "
            f"(found {sys.version_info.major}.{sys.version_info.minor})."
        )

    missing = find_missing_commands(required_build_commands(system))
    if missing:
        issues.append(f"Missing build commands: {', '.join(missing)}.")

    if shutil.which("buildozer") is None:
        issues.append(
            "Buildozer is missing; run through scripts/android.sh or install "
            "the Android build dependency group."
        )

    missing_modules = find_missing_python_modules(("pip",))
    if missing_modules:
        issues.append(
            "The Android environment is missing pip; synchronize its build "
            "dependency group."
        )

    java_major = javac_major_version()
    if java_major is not None and java_major != 17:
        issues.append(f"Java 17 is required (found Java {java_major}).")

    return tuple(issues)


def print_environment_report() -> tuple[str, ...]:
    print(f"Host: {platform.system()} {platform.machine()}")
    print(f"Python: {platform.python_version()}")
    for package in ("kivy", "buildozer", "pip"):
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = "not installed"
        print(f"{package}: {version}")

    issues = build_environment_issues()
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
    else:
        print("Android build environment: ready")
    return issues


def run_local_prototype() -> int:
    source = prepare_android_source()
    return subprocess.run(
        [sys.executable, str(source / "main.py")],
        cwd=source,
        check=False,
    ).returncode


def build_debug_apk() -> int:
    issues = print_environment_report()
    if issues:
        return 1

    prepare_android_source()
    buildozer = shutil.which("buildozer")
    assert buildozer is not None
    return subprocess.run(
        [buildozer, "--verbose", "android", "debug"],
        cwd=ANDROID_DIR,
        check=False,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Develop and build the isolated MoonTransfer Android prototype."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Check Android build prerequisites.")
    subparsers.add_parser("prepare", help="Generate the Android source tree.")
    subparsers.add_parser("run", help="Run the Kivy scaffold on the host.")
    subparsers.add_parser("build", help="Build an arm64 debug APK.")
    args = parser.parse_args()

    if args.command == "doctor":
        return int(bool(print_environment_report()))
    if args.command == "prepare":
        print(prepare_android_source())
        return 0
    if args.command == "run":
        return run_local_prototype()
    if args.command == "build":
        return build_debug_apk()
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

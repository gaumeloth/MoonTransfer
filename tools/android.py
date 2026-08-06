from __future__ import annotations

import argparse
import hashlib
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
ANDROID_P4A_BUILD_ROOT = (
    ROOT
    / "build"
    / "android"
    / "buildozer"
    / "android"
    / "platform"
    / "build-arm64-v8a"
)
CROC_RECIPE_PATH = ANDROID_DIR / "recipes" / "croc" / "__init__.py"
CROC_RECIPE_MARKER = (
    ROOT / "build" / "android" / "buildozer" / ".moontransfer-croc-recipe.sha256"
)
CROC_BUILD_CACHE_PATHS = (
    Path("packages/croc"),
    Path("build/other_builds/croc"),
    Path("build/libs_collections/moontransfer"),
    Path("dists/moontransfer"),
)
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
    "go",
)
MINIMUM_GO_VERSION = (1, 25)
GO_VERSION_RE = re.compile(r"\bgo version go(\d+)\.(\d+)")
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


def parse_go_version(output: str) -> tuple[int, int] | None:
    match = GO_VERSION_RE.search(output)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def go_version() -> tuple[int, int] | None:
    go = shutil.which("go")
    if go is None:
        return None
    result = subprocess.run(
        [go, "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    return parse_go_version(result.stdout + result.stderr)


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

    if shutil.which("go") is not None:
        installed_go = go_version()
        if installed_go is None:
            issues.append("Unable to determine the installed Go version.")
        elif installed_go < MINIMUM_GO_VERSION:
            required = ".".join(str(part) for part in MINIMUM_GO_VERSION)
            found = ".".join(str(part) for part in installed_go)
            issues.append(f"Go {required} or newer is required (found Go {found}).")

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


def croc_recipe_fingerprint(recipe_path: Path = CROC_RECIPE_PATH) -> str:
    return hashlib.sha256(recipe_path.read_bytes()).hexdigest()


def invalidate_stale_croc_build_cache(
    *,
    build_root: Path = ANDROID_P4A_BUILD_ROOT,
    recipe_path: Path = CROC_RECIPE_PATH,
    marker_path: Path = CROC_RECIPE_MARKER,
) -> tuple[str, bool]:
    fingerprint = croc_recipe_fingerprint(recipe_path)
    try:
        cached_fingerprint = marker_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        cached_fingerprint = ""

    if cached_fingerprint == fingerprint:
        return fingerprint, False

    removed = False
    for relative_path in CROC_BUILD_CACHE_PATHS:
        path = build_root / relative_path
        if path.is_symlink():
            raise RuntimeError(f"Refusing to remove symbolic build path: {path}")
        if path.exists():
            if not path.is_dir():
                raise RuntimeError(f"Expected Android build directory: {path}")
            shutil.rmtree(path)
            removed = True

    if removed:
        print("Android croc recipe changed; removed its stale native build cache.")
    return fingerprint, removed


def record_croc_recipe_fingerprint(
    fingerprint: str,
    marker_path: Path = CROC_RECIPE_MARKER,
) -> None:
    if marker_path.is_symlink():
        raise RuntimeError(f"Refusing to replace symbolic build marker: {marker_path}")
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker_path.with_name(f"{marker_path.name}.tmp")
    temporary.write_text(f"{fingerprint}\n", encoding="ascii")
    temporary.replace(marker_path)


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
    croc_fingerprint, _ = invalidate_stale_croc_build_cache()
    buildozer = shutil.which("buildozer")
    assert buildozer is not None
    result = subprocess.run(
        [buildozer, "--verbose", "android", "debug"],
        cwd=ANDROID_DIR,
        check=False,
    )
    if result.returncode == 0:
        record_croc_recipe_fingerprint(croc_fingerprint)
    return result.returncode


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

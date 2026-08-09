from __future__ import annotations

import argparse
import hashlib
import io
import importlib.metadata
import importlib.util
import json
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath

from tools.build_metadata import BuildMetadata, VERSION_RE, create_build_metadata
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
ANDROID_DIST_DIR = ROOT / "dist" / "android"
ANDROID_RELEASE_DIR = ROOT / "release"
ANDROID_ARCHITECTURE = "arm64-v8a"
MAX_PRIVATE_ARCHIVE_BYTES = 64 * 1024 * 1024
REQUIRED_APK_MEMBERS = frozenset(
    {
        "AndroidManifest.xml",
        "assets/private.tar",
        "classes.dex",
        f"lib/{ANDROID_ARCHITECTURE}/libcroc.so",
        f"lib/{ANDROID_ARCHITECTURE}/libmain.so",
        f"lib/{ANDROID_ARCHITECTURE}/libpython3.13.so",
    }
)
REQUIRED_PRIVATE_MEMBERS = frozenset(
    {
        "main.pyc",
        "moontransfer/build-info.json",
        "moontransfer/protocol.pyc",
        "moontransfer_android/application.pyc",
        "moontransfer_android/licenses/croc.txt",
        "moontransfer_android/moontransfer.kv",
        "moontransfer_android/service.pyc",
        "moontransfer_android/transport.pyc",
    }
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


def build_debug_apk(
    *,
    version: str | None = None,
    commit: str | None = None,
) -> int:
    issues = print_environment_report()
    if issues:
        return 1

    prepare_android_source(version=version, commit=commit)
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


def _validate_archive_names(names: Sequence[str], *, label: str) -> None:
    if len(names) != len(set(names)):
        raise RuntimeError(f"{label} contains duplicate member names.")
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError(f"{label} contains an unsafe member path: {name!r}.")


def _read_private_build_info(
    archive: zipfile.ZipFile,
) -> tuple[dict[str, object], tuple[str, ...]]:
    private_info = archive.getinfo("assets/private.tar")
    if private_info.file_size > MAX_PRIVATE_ARCHIVE_BYTES:
        raise RuntimeError(
            "Android private application archive is unexpectedly large."
        )

    private_data = archive.read(private_info)
    try:
        with tarfile.open(fileobj=io.BytesIO(private_data), mode="r:gz") as private:
            names = tuple(member.name for member in private.getmembers())
            _validate_archive_names(
                names,
                label="Android private application archive",
            )
            missing = REQUIRED_PRIVATE_MEMBERS.difference(names)
            if missing:
                raise RuntimeError(
                    "Android private application archive is missing: "
                    + ", ".join(sorted(missing))
                )
            non_files = {
                name
                for name in REQUIRED_PRIVATE_MEMBERS
                if not private.getmember(name).isfile()
            }
            if non_files:
                raise RuntimeError(
                    "Android private application archive has invalid files: "
                    + ", ".join(sorted(non_files))
                )
            build_info_member = private.getmember("moontransfer/build-info.json")
            stream = private.extractfile(build_info_member)
            if stream is None:
                raise RuntimeError(
                    "Unable to read embedded Android build metadata."
                )
            raw_build_info = stream.read(8 * 1024 + 1)
    except (tarfile.TarError, KeyError) as exc:
        raise RuntimeError(
            "Android private application archive is not valid."
        ) from exc

    if len(raw_build_info) > 8 * 1024:
        raise RuntimeError("Embedded Android build metadata is too large.")
    try:
        build_info = json.loads(raw_build_info.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Embedded Android build metadata is not valid JSON."
        ) from exc
    if not isinstance(build_info, dict):
        raise RuntimeError("Embedded Android build metadata is not an object.")
    return build_info, names


def validate_debug_apk(
    apk: Path,
    *,
    expected: BuildMetadata,
) -> None:
    apk = apk.expanduser().absolute()
    if apk.is_symlink() or not apk.is_file():
        raise RuntimeError(f"Android APK not found or unsafe: {apk}")

    try:
        with zipfile.ZipFile(apk) as archive:
            names = tuple(archive.namelist())
            _validate_archive_names(names, label="Android APK")
            missing = REQUIRED_APK_MEMBERS.difference(names)
            if missing:
                raise RuntimeError(
                    "Android APK is missing: " + ", ".join(sorted(missing))
                )
            invalid_files = {
                name
                for name in REQUIRED_APK_MEMBERS
                if archive.getinfo(name).is_dir()
                or archive.getinfo(name).file_size == 0
            }
            if invalid_files:
                raise RuntimeError(
                    "Android APK has invalid files: "
                    + ", ".join(sorted(invalid_files))
                )
            if any(name.lower().endswith(".xcf") for name in names):
                raise RuntimeError(
                    "Android APK contains an excluded source asset."
                )

            architectures = {
                parts[1]
                for name in names
                if len(parts := PurePosixPath(name).parts) >= 3
                and parts[0] == "lib"
            }
            if architectures != {ANDROID_ARCHITECTURE}:
                found = ", ".join(sorted(architectures)) or "none"
                raise RuntimeError(
                    "Android APK contains unexpected native architectures: "
                    f"{found}."
                )

            build_info, private_names = _read_private_build_info(archive)
            if any(name.lower().endswith(".xcf") for name in private_names):
                raise RuntimeError(
                    "Android private application archive contains an excluded "
                    "source asset."
                )
            damaged = archive.testzip()
            if damaged is not None:
                raise RuntimeError(f"Android APK has a damaged member: {damaged}.")
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"Android APK is not a valid ZIP archive: {apk}") from exc

    expected_build_info = {
        "schema_version": expected.schema_version,
        "version": expected.version,
        "commit": expected.commit,
        "croc_version": expected.croc_version,
        "protocol_version": expected.protocol_version,
    }
    if build_info != expected_build_info:
        raise RuntimeError(
            "Embedded Android build metadata does not match the requested build."
        )


def package_debug_apk(
    metadata: BuildMetadata,
    *,
    dist_dir: Path = ANDROID_DIST_DIR,
    release_dir: Path = ANDROID_RELEASE_DIR,
) -> Path:
    if not VERSION_RE.fullmatch(metadata.version):
        raise RuntimeError(
            f"Unsafe Android artifact version: {metadata.version!r}."
        )

    dist_dir = dist_dir.expanduser().absolute()
    release_dir = release_dir.expanduser().absolute()
    source = (
        dist_dir
        / f"moontransfer-{metadata.version}-{ANDROID_ARCHITECTURE}-debug.apk"
    )
    validate_debug_apk(source, expected=metadata)

    if release_dir.is_symlink():
        raise RuntimeError(f"Refusing symbolic release directory: {release_dir}")
    release_dir.mkdir(parents=True, exist_ok=True)
    destination = (
        release_dir
        / f"MoonTransfer-{metadata.version}-android-arm64-debug.apk"
    )
    if destination.is_symlink() or (
        destination.exists() and not destination.is_file()
    ):
        raise RuntimeError(f"Refusing unsafe release artifact: {destination}")
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.is_symlink() or (
        temporary.exists() and not temporary.is_file()
    ):
        raise RuntimeError(f"Refusing unsafe temporary artifact: {temporary}")
    temporary.unlink(missing_ok=True)
    try:
        shutil.copy2(source, temporary)
        validate_debug_apk(temporary, expected=metadata)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    validate_debug_apk(destination, expected=metadata)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Develop and build the isolated MoonTransfer Android prototype."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Check Android build prerequisites.")
    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Generate the Android source tree.",
    )
    subparsers.add_parser("run", help="Run the Kivy scaffold on the host.")
    build_parser = subparsers.add_parser(
        "build",
        help="Build an arm64 debug APK.",
    )
    package_parser = subparsers.add_parser(
        "package",
        help="Validate and stage the arm64 debug APK as a CI artifact.",
    )
    for command_parser in (prepare_parser, build_parser, package_parser):
        command_parser.add_argument(
            "--version",
            help="Full version embedded in the Android build.",
        )
        command_parser.add_argument(
            "--commit",
            help="Git commit embedded in the Android build.",
        )
    args = parser.parse_args()

    if args.command == "doctor":
        return int(bool(print_environment_report()))
    if args.command == "prepare":
        print(
            prepare_android_source(
                version=args.version,
                commit=args.commit,
            )
        )
        return 0
    if args.command == "run":
        return run_local_prototype()
    if args.command == "build":
        return build_debug_apk(
            version=args.version,
            commit=args.commit,
        )
    if args.command == "package":
        metadata = create_build_metadata(
            ROOT,
            version=args.version,
            commit=args.commit,
        )
        print(package_debug_apk(metadata))
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

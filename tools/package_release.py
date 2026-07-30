from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path


VERSION_RE = re.compile(r"^[0-9A-Za-z](?:[0-9A-Za-z._-]*[0-9A-Za-z])?$")


@dataclass(frozen=True)
class ReleaseTarget:
    name: str
    system: str
    architecture: str
    archive_suffix: str
    bundle_name: str
    executable_relative: Path
    croc_name: str


TARGETS = {
    "linux-x86_64": ReleaseTarget(
        name="linux-x86_64",
        system="Linux",
        architecture="x86_64",
        archive_suffix=".tar.gz",
        bundle_name="MoonTransfer",
        executable_relative=Path("MoonTransfer"),
        croc_name="croc",
    ),
    "linux-arm64": ReleaseTarget(
        name="linux-arm64",
        system="Linux",
        architecture="arm64",
        archive_suffix=".tar.gz",
        bundle_name="MoonTransfer",
        executable_relative=Path("MoonTransfer"),
        croc_name="croc",
    ),
    "macos-x86_64": ReleaseTarget(
        name="macos-x86_64",
        system="Darwin",
        architecture="x86_64",
        archive_suffix=".tar.gz",
        bundle_name="MoonTransfer.app",
        executable_relative=Path("Contents") / "MacOS" / "MoonTransfer",
        croc_name="croc",
    ),
    "macos-arm64": ReleaseTarget(
        name="macos-arm64",
        system="Darwin",
        architecture="arm64",
        archive_suffix=".tar.gz",
        bundle_name="MoonTransfer.app",
        executable_relative=Path("Contents") / "MacOS" / "MoonTransfer",
        croc_name="croc",
    ),
    "windows-x86_64": ReleaseTarget(
        name="windows-x86_64",
        system="Windows",
        architecture="x86_64",
        archive_suffix=".zip",
        bundle_name="MoonTransfer",
        executable_relative=Path("MoonTransfer.exe"),
        croc_name="croc.exe",
    ),
    "windows-arm64": ReleaseTarget(
        name="windows-arm64",
        system="Windows",
        architecture="arm64",
        archive_suffix=".zip",
        bundle_name="MoonTransfer",
        executable_relative=Path("MoonTransfer.exe"),
        croc_name="croc.exe",
    ),
}

RELEASE_DOCUMENT_NAMES = (
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "README.md",
    "README.it.md",
)


def normalize_architecture(machine: str) -> str:
    normalized = machine.strip().lower()
    if normalized in {"amd64", "x64", "x86_64"}:
        return "x86_64"
    if normalized in {"aarch64", "arm64"}:
        return "arm64"
    return normalized


def validate_version(value: str) -> str:
    version = value.removeprefix("v").strip()
    if not VERSION_RE.fullmatch(version):
        raise ValueError(
            "La versione può contenere solo lettere ASCII, numeri, punti, "
            "trattini e underscore."
        )
    return version


def validate_host(
    target: ReleaseTarget,
    *,
    system: str = platform.system(),
    machine: str = platform.machine(),
) -> None:
    architecture = normalize_architecture(machine)
    if target.system != system or target.architecture != architecture:
        raise RuntimeError(
            f"Target {target.name} incompatibile con host "
            f"{system}/{architecture or 'unknown'}."
        )


def read_croc_version(pyproject: Path) -> str:
    with pyproject.open("rb") as stream:
        data = tomllib.load(stream)
    try:
        version = data["tool"]["moontransfer"]["croc"]["version"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Versione croc mancante in pyproject.toml.") from exc
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("Versione croc non valida in pyproject.toml.")
    return version.strip().removeprefix("v")


def read_project_version(pyproject: Path) -> str:
    with pyproject.open("rb") as stream:
        data = tomllib.load(stream)
    try:
        version = data["project"]["version"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Versione progetto mancante in pyproject.toml.") from exc
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("Versione progetto non valida in pyproject.toml.")
    return version.strip()


def validate_package_version(pyproject: Path, value: str) -> str:
    version = validate_version(value)
    base_version = version.split("-", 1)[0]
    project_version = read_project_version(pyproject)
    if base_version != project_version:
        raise RuntimeError(
            f"Versione pacchetto {base_version} diversa dalla versione progetto "
            f"{project_version}."
        )
    return version


def find_bundled_croc(bundle: Path, croc_name: str) -> Path:
    candidates = sorted(
        (path for path in bundle.rglob(croc_name) if path.is_file()),
        key=lambda path: (len(path.parts), str(path)),
    )
    if not candidates:
        raise FileNotFoundError(f"{croc_name} non trovato nel bundle {bundle}.")
    return candidates[0]


def verify_croc_version(croc_path: Path, expected_version: str) -> None:
    result = subprocess.run(
        [str(croc_path), "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    output = "\n".join((result.stdout, result.stderr)).strip()
    if result.returncode != 0:
        raise RuntimeError(
            f"Il croc incluso non si avvia correttamente: {output or result.returncode}"
        )
    if not re.search(rf"\bv{re.escape(expected_version)}\b", output):
        raise RuntimeError(
            f"Versione croc inattesa: attesa v{expected_version}, output {output!r}."
        )


def validate_bundle(
    root: Path,
    target: ReleaseTarget,
    *,
    verify_croc: bool = True,
) -> Path:
    bundle = root / "dist" / target.bundle_name
    executable = bundle / target.executable_relative
    if not bundle.is_dir():
        raise FileNotFoundError(f"Bundle non trovato: {bundle}")
    if not executable.is_file():
        raise FileNotFoundError(f"Eseguibile MoonTransfer non trovato: {executable}")
    if os.name != "nt" and not os.access(executable, os.X_OK):
        raise PermissionError(f"Eseguibile MoonTransfer non avviabile: {executable}")

    croc_path = find_bundled_croc(bundle, target.croc_name)
    if verify_croc:
        verify_croc_version(croc_path, read_croc_version(root / "pyproject.toml"))
    return bundle


def release_documents(root: Path) -> tuple[Path, ...]:
    documents = tuple(root / name for name in RELEASE_DOCUMENT_NAMES)
    missing = tuple(path for path in documents if not path.is_file())
    if missing:
        paths = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Documenti release mancanti: {paths}")
    return documents


def archive_entries(
    source: Path,
    archive_root: str,
    documents: tuple[Path, ...],
) -> tuple[tuple[Path, Path], ...]:
    if source.name == "MoonTransfer":
        bundle_entries = tuple(
            (path, Path(archive_root) / path.name)
            for path in sorted(source.iterdir())
        )
    else:
        bundle_entries = ((source, Path(archive_root) / source.name),)

    document_entries = tuple(
        (path, Path(archive_root) / path.name) for path in documents
    )
    return (*bundle_entries, *document_entries)


def create_tar_archive(
    entries: tuple[tuple[Path, Path], ...],
    destination: Path,
) -> None:
    with tarfile.open(
        destination,
        mode="w:gz",
        format=tarfile.PAX_FORMAT,
        dereference=False,
    ) as archive:
        for source, archive_path in entries:
            archive.add(source, arcname=str(archive_path), recursive=True)


def create_zip_archive(
    entries: tuple[tuple[Path, Path], ...],
    destination: Path,
) -> None:
    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for source, archive_path in entries:
            archive.write(source, archive_path)
            if source.is_dir():
                for path in sorted(source.rglob("*")):
                    relative = path.relative_to(source)
                    archive.write(path, archive_path / relative)


def create_release_package(
    root: Path,
    target: ReleaseTarget,
    version: str,
    *,
    output_dir: Path | None = None,
    verify_croc: bool = True,
) -> Path:
    bundle = validate_bundle(root, target, verify_croc=verify_croc)
    release_dir = output_dir or root / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    normalized_version = validate_package_version(
        root / "pyproject.toml",
        version,
    )
    destination = release_dir / (
        f"MoonTransfer-{normalized_version}-{target.name}{target.archive_suffix}"
    )
    archive_root = f"MoonTransfer-{normalized_version}"
    entries = archive_entries(
        bundle,
        archive_root,
        release_documents(root),
    )
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.unlink(missing_ok=True)

    try:
        if target.archive_suffix == ".zip":
            create_zip_archive(entries, temporary)
        else:
            create_tar_archive(entries, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)

    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and package a MoonTransfer onedir build.",
    )
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="output directory (default: release/)",
    )
    parser.add_argument(
        "--skip-host-check",
        action="store_true",
        help="package a target that does not match the current host",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    target = TARGETS[args.target]
    if not args.skip_host_check:
        validate_host(target)

    package = create_release_package(
        root,
        target,
        args.version,
        output_dir=args.output_dir,
    )
    print(f"[ok] Pacchetto release: {package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

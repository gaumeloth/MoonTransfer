from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from tools.build_metadata import create_build_metadata, write_build_metadata


def run(cmd: list[str], *, cwd: Path) -> None:
    print()
    print("$ " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the MoonTransfer desktop onedir bundle."
    )
    parser.add_argument(
        "--version",
        help="Full version embedded in the bundle (for example 0.1.0-alpha.3).",
    )
    parser.add_argument(
        "--commit",
        help="Git commit embedded in the bundle; defaults to the current HEAD.",
    )
    args = parser.parse_args()

    root = ROOT

    fetch_croc = root / "tools" / "fetch_croc.py"
    spec_file = root / "MoonTransfer.spec"

    if not fetch_croc.exists():
        raise FileNotFoundError(f"File mancante: {fetch_croc}")

    if not spec_file.exists():
        raise FileNotFoundError(f"File mancante: {spec_file}")

    metadata_path = root / "build" / "generated" / "build-info.json"
    metadata = create_build_metadata(
        root,
        version=args.version,
        commit=args.commit,
    )
    write_build_metadata(metadata_path, metadata)
    print(f"[build] Versione: {metadata.version}")
    print(f"[build] Commit: {metadata.commit or 'non disponibile'}")
    print(f"[build] Metadati: {metadata_path.relative_to(root)}")

    run([sys.executable, str(fetch_croc)], cwd=root)

    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(spec_file),
        ],
        cwd=root,
    )

    print()
    print("[done] Build completata.")
    if sys.platform == "darwin":
        print("[done] Output: dist/MoonTransfer.app")
    else:
        print("[done] Output: dist/MoonTransfer/")


if __name__ == "__main__":
    main()

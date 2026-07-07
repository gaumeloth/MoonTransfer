from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], *, cwd: Path) -> None:
    print()
    print("$ " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd))


def main() -> None:
    root = Path(__file__).resolve().parent.parent

    fetch_croc = root / "tools" / "fetch_croc.py"
    spec_file = root / "MoonTransfer.spec"

    if not fetch_croc.exists():
        raise FileNotFoundError(f"File mancante: {fetch_croc}")

    if not spec_file.exists():
        raise FileNotFoundError(f"File mancante: {spec_file}")

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
    print("[done] Output: dist/MoonTransfer/")


if __name__ == "__main__":
    main()

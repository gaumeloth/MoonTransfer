from __future__ import annotations

import os
import re
import shlex
import shutil
import sys
from pathlib import Path


CROC_SECRET_ENV = "CROC_SECRET"
CODE_RE = re.compile(r"Code is:\s*(.+)\s*$")


def executable_name() -> str:
    return "croc.exe" if os.name == "nt" else "croc"


def find_executable() -> str | None:
    exe_name = executable_name()
    candidates: list[Path] = []

    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(Path(bundle_dir) / exe_name)

    root = Path(__file__).resolve().parents[2]
    candidates.append(root / "third_party" / "croc" / exe_name)
    candidates.append(Path(__file__).resolve().parent / exe_name)

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return shutil.which(exe_name)


def command_preview(program: str, args: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in [program, *args])


def parse_send_code(line: str) -> str | None:
    match = CODE_RE.search(line)
    if not match:
        return None

    code = match.group(1).strip()
    return code or None


def build_send_args(path: Path, *, code: str | None = None) -> list[str]:
    args = [
        "--ignore-stdin",
        "--disable-clipboard",
        "send",
        "--no-local",
    ]

    if code:
        args.extend(["--code", code])

    args.append(str(path))
    return args


def build_receive_args(code: str | None = None) -> list[str]:
    args = ["--ignore-stdin", "--yes", "--overwrite"]
    if code:
        args.append(code)
    return args


def build_hidden_code_receive_preview(program: str, args: list[str]) -> str:
    hidden_args = [*args[:-1], "<hidden>"] if args else args
    return command_preview(program, hidden_args)

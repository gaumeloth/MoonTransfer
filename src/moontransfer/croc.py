from __future__ import annotations

import os
import re
import shlex
import shutil
import sys
from pathlib import Path


CROC_SECRET_ENV = "CROC_SECRET"
NON_CLASSIC_ARG = "--classic=false"
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


def build_send_args(path: Path) -> list[str]:
    return [
        NON_CLASSIC_ARG,
        "--ignore-stdin",
        "--disable-clipboard",
        "send",
        "--no-local",
        str(path),
    ]


def build_receive_args() -> list[str]:
    return [NON_CLASSIC_ARG, "--ignore-stdin", "--yes", "--overwrite"]


def build_prompted_receive_args() -> list[str]:
    return [NON_CLASSIC_ARG, "--overwrite"]


def build_process_environment(
    config_dir: Path,
    *,
    secret: str | None = None,
) -> dict[str, str]:
    home = config_dir / "home"
    xdg_config = config_dir / "xdg"
    appdata = config_dir / "appdata"
    localappdata = config_dir / "localappdata"
    for directory in (home, xdg_config, appdata, localappdata):
        directory.mkdir(parents=True, exist_ok=True)

    env = {
        "XDG_CONFIG_HOME": str(xdg_config),
        "APPDATA": str(appdata),
        "LOCALAPPDATA": str(localappdata),
        "HOME": str(home),
    }
    if secret is not None:
        env[CROC_SECRET_ENV] = secret
    return env


def build_secret_preview(program: str, args: list[str]) -> str:
    return f"{CROC_SECRET_ENV}=<hidden> {command_preview(program, args)}"

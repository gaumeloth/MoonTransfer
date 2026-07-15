from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path


def folder_open_command(
    path: Path,
    *,
    platform_name: str = sys.platform,
    which: Callable[[str], str | None] = shutil.which,
) -> list[str] | None:
    if platform_name == "darwin":
        opener = which("open")
        return [opener or "open", str(path)]

    if platform_name.startswith(("linux", "freebsd", "openbsd", "netbsd")):
        for command in (("xdg-open",), ("gio", "open"), ("kde-open5",), ("kde-open",)):
            opener = which(command[0])
            if opener:
                return [opener, *command[1:], str(path)]

    return None


def external_process_environment(
    env: Mapping[str, str] | None = None,
    *,
    frozen: bool | None = None,
) -> dict[str, str]:
    clean_env = dict(os.environ if env is None else env)
    running_frozen = getattr(sys, "frozen", False) if frozen is None else frozen

    original_library_path = clean_env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original_library_path is not None:
        if original_library_path:
            clean_env["LD_LIBRARY_PATH"] = original_library_path
        else:
            clean_env.pop("LD_LIBRARY_PATH", None)
    elif running_frozen:
        clean_env.pop("LD_LIBRARY_PATH", None)

    if running_frozen:
        for key in (
            "QT_PLUGIN_PATH",
            "QML2_IMPORT_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
        ):
            clean_env.pop(key, None)

    return clean_env


@dataclass(frozen=True)
class FolderOpenResult:
    opened: bool
    error: str = ""


def _folder_open_error(command: list[str], exit_code: int, stderr: str) -> str:
    details = stderr.strip()
    if not details:
        details = f"{Path(command[0]).name} è terminato con codice {exit_code}."

    return details[:1200]


def open_folder(path: Path) -> FolderOpenResult:
    if not path.is_dir():
        return FolderOpenResult(False, "La cartella non esiste.")

    if sys.platform.startswith("win"):
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return FolderOpenResult(True)
        except OSError as exc:
            return FolderOpenResult(False, str(exc))

    command = folder_open_command(path)
    if not command:
        return FolderOpenResult(False, "Nessun comando di apertura disponibile.")

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=external_process_environment(),
            start_new_session=True,
        )
    except OSError as exc:
        return FolderOpenResult(False, str(exc))

    try:
        _, stderr = process.communicate(timeout=1.0)
    except subprocess.TimeoutExpired:
        if process.stderr:
            process.stderr.close()
        return FolderOpenResult(True)

    if process.returncode == 0:
        return FolderOpenResult(True)

    return FolderOpenResult(
        False,
        _folder_open_error(command, process.returncode or 1, stderr),
    )

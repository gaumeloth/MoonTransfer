from __future__ import annotations

import json
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from moontransfer import __version__
from moontransfer.protocol import PROTOCOL_VERSION


BUILD_INFO_FILENAME = "build-info.json"
BUILD_INFO_SCHEMA_VERSION = 1
MAX_BUILD_INFO_BYTES = 8 * 1024
_VERSION_RE = re.compile(r"^[0-9A-Za-z](?:[0-9A-Za-z._+-]*[0-9A-Za-z])?$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")


@dataclass(frozen=True, slots=True)
class BuildInfo:
    version: str
    commit: str | None
    croc_version: str | None
    protocol_version: int
    embedded: bool

    @property
    def short_commit(self) -> str:
        return self.commit[:12] if self.commit else "non disponibile"

    def diagnostics(self) -> str:
        system = platform.system() or "sconosciuto"
        architecture = platform.machine() or "sconosciuta"
        python_version = ".".join(str(part) for part in sys.version_info[:3])
        return "\n".join(
            (
                f"MoonTransfer: {self.version}",
                f"Commit: {self.commit or 'non disponibile'}",
                f"croc incorporato: {self.croc_version or 'non disponibile'}",
                f"Protocollo MoonTransfer: {self.protocol_version}",
                f"Python: {python_version}",
                f"Sistema: {system} ({architecture})",
                (
                    "Metadati build: incorporati"
                    if self.embedded
                    else "Metadati build: fallback da sorgente"
                ),
            )
        )


def _fallback_build_info() -> BuildInfo:
    return BuildInfo(
        version=f"{__version__}-dev",
        commit=None,
        croc_version=None,
        protocol_version=PROTOCOL_VERSION,
        embedded=False,
    )


def _validated_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
        raise ValueError(f"Campo {field} non valido nei metadati di build.")
    return value


def _parse_build_info(data: object) -> BuildInfo:
    if not isinstance(data, dict):
        raise ValueError("I metadati di build devono essere un oggetto JSON.")
    if data.get("schema_version") != BUILD_INFO_SCHEMA_VERSION:
        raise ValueError("Versione dello schema dei metadati non supportata.")

    commit = data.get("commit")
    if commit is not None and (
        not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit)
    ):
        raise ValueError("Commit non valido nei metadati di build.")

    protocol_version = data.get("protocol_version")
    if (
        not isinstance(protocol_version, int)
        or isinstance(protocol_version, bool)
        or protocol_version < 1
    ):
        raise ValueError("Versione del protocollo non valida nei metadati.")
    if protocol_version != PROTOCOL_VERSION:
        raise ValueError("I metadati non corrispondono al protocollo runtime.")

    return BuildInfo(
        version=_validated_text(data.get("version"), field="version"),
        commit=commit,
        croc_version=_validated_text(
            data.get("croc_version"),
            field="croc_version",
        ),
        protocol_version=protocol_version,
        embedded=True,
    )


def load_build_info(path: Path | None = None) -> BuildInfo:
    metadata_path = path or Path(__file__).resolve().with_name(
        BUILD_INFO_FILENAME
    )
    try:
        if metadata_path.stat().st_size > MAX_BUILD_INFO_BYTES:
            return _fallback_build_info()
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        return _parse_build_info(data)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return _fallback_build_info()


CURRENT_BUILD = load_build_info()

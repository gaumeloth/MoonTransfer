from __future__ import annotations

import ast
import json
import re
import subprocess
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

VERSION_RE = re.compile(r"^[0-9A-Za-z](?:[0-9A-Za-z._+-]*[0-9A-Za-z])?$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")


@dataclass(frozen=True, slots=True)
class BuildMetadata:
    schema_version: int
    version: str
    commit: str | None
    croc_version: str
    protocol_version: int


def read_project_settings(pyproject: Path) -> tuple[str, str]:
    with pyproject.open("rb") as stream:
        data = tomllib.load(stream)
    try:
        project_version = data["project"]["version"]
        croc_version = data["tool"]["moontransfer"]["croc"]["version"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            "Versione MoonTransfer o croc mancante in pyproject.toml."
        ) from exc

    return (
        _validate_version(project_version, field="project.version"),
        _validate_version(croc_version, field="croc.version"),
    )


def read_integer_constant(path: Path, name: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        try:
            value = ast.literal_eval(statement.value)
        except (SyntaxError, ValueError):
            break
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        break
    raise RuntimeError(f"Costante intera {name} non valida o mancante in {path}.")


def _validate_version(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
        raise ValueError(f"Valore non valido per {field}: {value!r}")
    return value


def _git_output(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def git_worktree_is_clean(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and not result.stdout.strip()


def resolve_commit(root: Path, explicit: str | None = None) -> str | None:
    commit = (
        explicit
        if explicit is not None
        else _git_output(root, "rev-parse", "--verify", "HEAD")
    )
    if commit is None:
        return None
    commit = commit.strip().lower()
    if not COMMIT_RE.fullmatch(commit):
        raise ValueError(f"Commit di build non valido: {commit!r}")
    return commit


def resolve_build_version(
    root: Path,
    project_version: str,
    *,
    commit: str | None,
    explicit: str | None = None,
) -> str:
    if explicit is not None:
        return _validate_version(explicit.strip(), field="build.version")

    exact_tag = _git_output(
        root,
        "describe",
        "--tags",
        "--exact-match",
        "--match",
        "v[0-9]*",
    )
    if exact_tag and git_worktree_is_clean(root):
        candidate = exact_tag.removeprefix("v")
        if VERSION_RE.fullmatch(candidate):
            return candidate

    suffix = f".{commit[:12]}" if commit else ""
    return f"{project_version}-dev{suffix}"


def create_build_metadata(
    root: Path,
    *,
    version: str | None = None,
    commit: str | None = None,
) -> BuildMetadata:
    root = root.resolve()
    project_version, croc_version = read_project_settings(
        root / "pyproject.toml"
    )
    package = root / "src" / "moontransfer"
    schema_version = read_integer_constant(
        package / "build_info.py",
        "BUILD_INFO_SCHEMA_VERSION",
    )
    protocol_version = read_integer_constant(
        package / "protocol.py",
        "PROTOCOL_VERSION",
    )
    resolved_commit = resolve_commit(root, commit)
    resolved_version = resolve_build_version(
        root,
        project_version,
        commit=resolved_commit,
        explicit=version,
    )
    if resolved_version.split("-", 1)[0] != project_version:
        raise ValueError(
            "La versione completa della build non corrisponde alla versione "
            f"progetto {project_version}: {resolved_version}"
        )
    return BuildMetadata(
        schema_version=schema_version,
        version=resolved_version,
        commit=resolved_commit,
        croc_version=croc_version,
        protocol_version=protocol_version,
    )


def write_build_metadata(path: Path, metadata: BuildMetadata) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(asdict(metadata), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)

import os
import sys
import time
import json
import re
import platform
import shutil
import tarfile
import zipfile
import hashlib
from pathlib import Path
from urllib.request import urlopen, Request

CROC_OWNER = "schollz"
CROC_REPO = "croc"
USER_AGENT = "moontransfer-build/1.0"


def _is_within_dir(base: Path, target: Path) -> bool:
    base = base.resolve()
    target = target.resolve()
    return str(target).startswith(str(base) + os.sep)


def safe_extract_tar(t: tarfile.TarFile, dst: Path) -> None:
    dst = dst.resolve()
    for m in t.getmembers():
        out = (dst/m.name)
        if not _is_within_dir(dst, out):
            raise RuntimeError(f"Path traversal nel tar: {m.name}")
    t.extractall(dst)


def safe_extract_zip(z: zipfile.ZipFile, dst: Path) -> None:
    dst = dst.resolve()
    for name in z.namelist():
        out = (dst/name)
        if not _is_within_dir(dst, out):
            raise RuntimeError(f"Path traversal nello zip: {name}")
    z.extractall(dst)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_checksum(txt: str) -> dict[str, str]:
    out = {}
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            out[parts[1]] = parts[0].lower()
    return out


def verify_archive(asset: str, archive: Path, version: str) -> None:
    checksum_name = f"croc_v{version}_checksums.txt"
    url = f"https://github.com/schollz/croc/releases/download/v{
        version}/{checksum_name}"
    checksum_map = parse_checksum(http_get(url).decode("utf-8", "replace"))
    expected = checksum_map.get(asset)
    if not expected:
        raise RuntimeError(f"Checksum non trovato per asset: {
                           asset} (nel file{checksum_name})")
    got = sha256_file(archive)
    if got != expected:
        raise RuntimeError(f"SHA256 mismatch per {asset}\n expected={
                           expected}\n got     ={got}")


def http_get(url: str, *, headers: dict[str, str] | None = None, timeout: int = 60,) -> bytes:
    final_headers = {"User-Agent": USER_AGENT}

    if headers:
        final_headers.update(headers)

    req = Request(url, headers=final_headers)

    with urlopen(req, timeout=timeout) as r:
        return r.read()


def github_api_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


def normalize_version(version: str) -> str:
    """
    Normalizza stringhe tipo:
      'v10.3.1' -> '10.3.1'
      '10.3.1'  -> '10.3.1'
    """
    version = version.strip()

    if version.startswith("v"):
        version = version[1:]

    return version


def parse_version(version: str) -> tuple[int, int, int]:
    """
    Parser minimale per versioni croc in forma MAJOR.MINOR.PATCH.

    Esempi:
      10.3.1      -> (10, 3, 1)
      v10.3.1     -> (10, 3, 1)
      10.3.1-beta -> (10, 3, 1)

    Per il nostro caso va bene perché /releases/latest non dovrebbe restituire
    prerelease, quindi normalmente avremo versioni pulite tipo 10.3.1.
    """
    version = normalize_version(version)

    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"Formato versione non supportato: {version!r}")

    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def compare_versions(left: str, right: str) -> int:
    """
    Ritorna:
      -1 se left < right
       0 se left == right
       1 se left > right
    """
    l_tuple = parse_version(left)
    r_tuple = parse_version(right)

    if l_tuple < r_tuple:
        return -1
    if l_tuple > r_tuple:
        return 1
    return 0


def read_installed_version(version_file: Path) -> str | None:
    if not version_file.exists():
        return None

    value = version_file.read_text(encoding="utf-8").strip()

    if not value:
        return None

    return normalize_version(value)


def get_latest_croc_version() -> str:
    api_url = (
        f"https://api.github.com/repos/"
        f"{CROC_OWNER}/{CROC_REPO}/releases/latest"
    )

    raw = http_get(api_url, headers=github_api_headers())
    data = json.loads(raw.decode("utf-8"))

    tag_name = data.get("tag_name")
    if not tag_name:
        raise RuntimeError(
            "GitHub API: campo tag_name mancante nella latest release")

    return normalize_version(tag_name)


def download_atomic(url: str, dest: Path, *, timeout: int = 60, chunk_size: int = 1024 * 1024, retries: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")

    if tmp.exists():
        tmp.unlink()

    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=timeout) as r:
                total = r.headers.get("Content-Length")
                total_int = int(total) if total and total.isdigit() else None

                downloaded = 0
                last_print = 0.0

                with tmp.open("wb") as f:
                    while True:
                        chunk = r.read(chunk_size)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded += len(chunk)

                        if sys.stdout.isatty():
                            now = time.time()
                            if now - last_print >= 0.1:
                                if total_int:
                                    pct = downloaded * 100 // total_int
                                    print(f"\r[dl] {dest.name} {pct:3d}% ({
                                          downloaded}/{total_int} bytes)", end="", flush=True)
                                else:
                                    print(f"\r[dl] {dest.name} ({
                                          downloaded} bytes)", end="", flush=True)
                                last_print = now

                if sys.stdout.isatty():
                    print()

            tmp.replace(dest)
            return

        except Exception as e:
            if tmp.exists():
                tmp.unlink()

            if attempt == retries:
                raise RuntimeError(f"Download fallito dopo {retries} tentativi: {
                                   url}\nUltimo errore: {e}") from e

            time.sleep(0.5 * attempt)


def pick_asset(version: str) -> str:
    sysname = platform.system().lower()
    mach = platform.machine().lower()

    if sysname == "windows":
        return f"croc_v{version}_Windows-64bit.zip"

    if sysname == "darwin":
        if mach in ("arm64", "aarch64"):
            return f"croc_v{version}_macOS-ARM64.tar.gz"
        return f"croc_v{version}_macOS-64bit.tar.gz"

    if sysname == "linux":
        if mach in ("arm64", "aarch64"):
            return f"croc_v{version}_Linux-ARM64.tar.gz"
        return f"croc_v{version}_Linux-64bit.tar.gz"

    raise RuntimeError(f"OS non supportato: {platform.system()}")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    outdir = root / "third_party" / "croc"
    outdir.mkdir(parents=True, exist_ok=True)

    exe = "croc.exe" if os.name == "nt" else "croc"
    dest = outdir / exe
    version_file = outdir / "VERSION"

    installed_version = read_installed_version(version_file)

    print("[check] verifico ultima versione disponibile online")
    latest_version = get_latest_croc_version()

    if installed_version:
        print(f"[local] croc installato: v{installed_version}")
    else:
        print("[local] croc non risulta installato")

    print(f"[remote] ultima versione disponibile: v{latest_version}")

    if dest.exists() and installed_version:
        cmp = compare_versions(installed_version, latest_version)

        if cmp == 0:
            print(f"[ok] croc già aggiornato (v{installed_version}): {dest}")
            return

        if cmp > 0:
            print(
                f"[warn] versione locale v{installed_version} "
                f"più recente della latest online v{
                    latest_version}; non aggiorno"
            )
            return

        print(
            f"[update] aggiorno croc da v{installed_version} "
            f"a v{latest_version}"
        )
    else:
        print(f"[install] installo croc v{latest_version}")

    asset = pick_asset(latest_version)
    url = (
        f"https://github.com/{CROC_OWNER}/{CROC_REPO}/releases/download/"
        f"v{latest_version}/{asset}"
    )

    cache = root / ".cache"
    cache.mkdir(exist_ok=True)
    archive = cache / asset

    if archive.exists():
        try:
            verify_archive(asset, archive, latest_version)
            print(f"[cache] archivio valido: {archive.name}")
        except Exception as e:
            print(f"[warn] cahe non valida({e}); riscarico\n[fetch] {url}")
            download_atomic(url, archive)
            verify_archive(asset, archive, latest_version)
            print("[ok] checksum verificato")
    else:
        print(f"[fetch] {url}")
        download_atomic(url, archive)
        verify_archive(asset, archive, latest_version)
        print("[ok] checksum verificato")

    extract_dir = cache / "croc_extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir()

    if asset.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as z:
            safe_extract_zip(z, extract_dir)
    else:
        with tarfile.open(archive, "r:gz") as t:
            safe_extract_tar(t, extract_dir)

    found = next(extract_dir.rglob(exe), None)
    if not found:
        raise RuntimeError(f"croc non trovato nell'archivio estratto")

    shutil.copy2(found, dest)
    if os.name != "nt":
        dest.chmod(dest.stat().st_mode | 0o111)

    print(f"[ok] croc pronto: {dest}")

    version_file.write_text(latest_version + "\n", encoding="utf-8")
    print(f"[ok] marker versione scritto: {version_file}")


if __name__ == "__main__":
    main()

"""Sign an already-built release APK without exposing keys to the build toolchain."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from tools.android import ROOT, validate_apk, validate_share_manifest, validate_version_code
from tools.build_metadata import create_build_metadata


PREFIX = "MOONTRANSFER_ANDROID_"
ANDROID = "{http://schemas.android.com/apk/res/android}"


def certificate_digest(value: str) -> str:
    digest = value.replace(":", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Expected a SHA-256 signing certificate fingerprint (64 hex digits).")
    return digest


def sdk_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    roots = [
        Path(os.environ[key]).expanduser()
        for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT") if os.environ.get(key)
    ]
    roots.append(Path.home() / ".buildozer/android/platform/android-sdk")
    patterns = (
        ("cmdline-tools/*/bin/apkanalyzer", "tools/bin/apkanalyzer")
        if name == "apkanalyzer" else (f"build-tools/*/{name}",)
    )
    for root in roots:
        for pattern in patterns:
            candidates = [p for p in root.glob(pattern) if p.is_file() and os.access(p, os.X_OK)]
            if candidates:
                return str(max(candidates, key=lambda p: tuple(
                    int(n) for n in re.findall(r"\d+", str(p.relative_to(root)))
                )))
    raise RuntimeError(f"Android SDK tool not found: {name}. Set ANDROID_HOME or PATH.")


def run_tool(command: list[str], *, env: dict[str, str] | None = None) -> bytes:
    # Never relay tool diagnostics: failures may include secret arguments or values.
    result = subprocess.run(command, env=env, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name} failed (exit {result.returncode}). Check signing configuration and SDK.")
    return result.stdout


def validate_release_manifest(xml: str, *, version: str, version_code: int) -> None:
    root = ET.fromstring(xml)
    app = root.find("application")
    sdk = root.find("uses-sdk")
    if (
        root.tag != "manifest"
        or root.get("package") != "io.github.gaumeloth.moontransfer"
        or root.get(ANDROID + "versionName") != version
        or root.get(ANDROID + "versionCode") != str(validate_version_code(version_code))
        or app is None
        or app.get(ANDROID + "debuggable", "false") != "false"
        or app.get(ANDROID + "testOnly", "false") != "false"
        or sdk is None
        or sdk.get(ANDROID + "minSdkVersion") != "24"
        or sdk.get(ANDROID + "targetSdkVersion") != "36"
    ):
        raise RuntimeError("APK is not the expected non-debuggable MoonTransfer release.")
    validate_share_manifest(xml)


def verify_signature(apk: Path, expected_sha256: str) -> None:
    output = run_tool([
        sdk_tool("apksigner"), "verify", "--verbose", "--print-certs", str(apk),
    ]).decode("utf-8")
    # Build Tools 37 uses scheme labels instead of the older "Signer #1" label.
    counts = re.findall(r"^Number of signers: (\d+)$", output, re.M)
    signers = re.findall(
        r"^(?:Signer #\d+|V\d+\.\d+ Signer:) certificate SHA-256 digest: ([0-9a-fA-F]+)$",
        output, re.M,
    )
    expected = certificate_digest(expected_sha256)
    if counts != ["1"] or not signers or any(certificate_digest(signer) != expected for signer in signers):
        raise RuntimeError("APK signing certificate does not match the expected SHA-256 fingerprint.")


def signing_environment(keystore: Path, alias: str) -> dict[str, str]:
    if keystore.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Keep the release keystore outside the repository.")
    if keystore.is_symlink() or not keystore.is_file() or not alias.strip():
        raise ValueError("A regular keystore file and a non-empty key alias are required.")
    environment = os.environ.copy()
    for name, prompt in (
        ("STORE_PASSWORD", "Keystore password: "),
        ("KEY_PASSWORD", "Key password (Enter = keystore password): "),
    ):
        key = PREFIX + name
        if not environment.get(key):
            if not sys.stdin.isatty():
                raise ValueError(f"Missing {key}; configure a secret or use an interactive terminal.")
            value = getpass.getpass(prompt)
            if name == "KEY_PASSWORD" and not value:
                value = environment[PREFIX + "STORE_PASSWORD"]
            if not value:
                raise ValueError("Signing passwords must not be empty.")
            environment[key] = value
    return environment


def sign_apk(
    apk: Path, output: Path, *, keystore: Path, alias: str,
    expected_sha256: str, version: str, commit: str, version_code: int,
) -> Path:
    validate_version_code(version_code)
    fingerprint = certificate_digest(expected_sha256)
    metadata = create_build_metadata(ROOT, version=version, commit=commit)
    validate_apk(apk, expected=metadata)
    xml = run_tool([sdk_tool("apkanalyzer"), "manifest", "print", str(apk)]).decode("utf-8")
    validate_release_manifest(xml, version=version, version_code=version_code)
    environment = signing_environment(keystore, alias)
    if output.exists() or output.is_symlink():
        raise ValueError("Refusing to overwrite an existing signed APK.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".android-sign-", dir=output.parent) as work:
        aligned = Path(work) / "aligned.apk"
        signed = Path(work) / "signed.apk"
        run_tool([sdk_tool("zipalign"), "-P", "16", "-f", "4", str(apk), str(aligned)])
        run_tool([
            sdk_tool("apksigner"), "sign", "--ks", str(keystore), "--ks-key-alias", alias,
            "--ks-pass", f"env:{PREFIX}STORE_PASSWORD",
            "--key-pass", f"env:{PREFIX}KEY_PASSWORD",
            "--v4-signing-enabled", "false", "--out", str(signed), str(aligned),
        ], env=environment)
        verify_signature(signed, fingerprint)
        run_tool([sdk_tool("zipalign"), "-c", "-P", "16", "4", str(signed)])
        validate_apk(signed, expected=metadata)
        # Publish atomically without replacing an existing file (same filesystem).
        os.link(signed, output)
    return output


def init_keystore(path: Path, alias: str) -> None:
    path = path.expanduser().absolute()
    if path.resolve().is_relative_to(ROOT.resolve()) or path.exists() or path.is_symlink():
        raise ValueError("Choose a new keystore path outside the repository; existing keys are never replaced.")
    if not sys.stdin.isatty():
        raise ValueError("Run key initialization yourself in an interactive terminal; do not send passwords in chat.")
    password = getpass.getpass("New keystore password (at least 12 characters): ")
    if len(password) < 12 or password != getpass.getpass("Repeat password: "):
        raise ValueError("Passwords must match and contain at least 12 characters.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = os.environ.copy()
    environment[PREFIX + "STORE_PASSWORD"] = password
    with tempfile.TemporaryDirectory(dir=path.parent) as work:
        temporary = Path(work) / "release.p12"
        run_tool([
            "keytool", "-genkeypair", "-keystore", str(temporary), "-storetype", "PKCS12",
            "-alias", alias, "-keyalg", "RSA", "-keysize", "4096", "-sigalg", "SHA256withRSA",
            "-validity", "10000", "-dname", "CN=MoonTransfer",
            "-storepass:env", PREFIX + "STORE_PASSWORD",
        ], env=environment)
        certificate = run_tool([
            "keytool", "-exportcert", "-keystore", str(temporary), "-alias", alias,
            "-storepass:env", PREFIX + "STORE_PASSWORD",
        ], env=environment)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as target, temporary.open("rb") as source:
            shutil.copyfileobj(source, target)
    print(f"Keystore created: {path}\nAlias: {alias}\nCertificate SHA-256: {hashlib.sha256(certificate).hexdigest()}")
    print("Back up the keystore and password separately before distributing any signed APK.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Interactively create the permanent key outside the repository.")
    init.add_argument("--keystore", type=Path, required=True)
    init.add_argument("--alias", default="moontransfer")
    sign = commands.add_parser("sign", help="Sign and verify an unsigned release APK.")
    sign.add_argument("--apk", type=Path, required=True)
    sign.add_argument("--output", type=Path, required=True)
    sign.add_argument("--keystore", type=Path, required=True)
    sign.add_argument("--alias", default="moontransfer")
    sign.add_argument("--expected-sha256", required=True)
    sign.add_argument("--version", required=True)
    sign.add_argument("--commit", required=True)
    sign.add_argument("--version-code", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            init_keystore(args.keystore, args.alias)
        else:
            print(sign_apk(
                args.apk.expanduser().absolute(), args.output.expanduser().absolute(),
                keystore=args.keystore.expanduser().absolute(), alias=args.alias,
                expected_sha256=args.expected_sha256, version=args.version, commit=args.commit,
                version_code=args.version_code,
            ))
    except (ValueError, RuntimeError, OSError, ET.ParseError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

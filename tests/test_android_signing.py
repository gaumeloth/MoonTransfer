from __future__ import annotations

import os
import base64
import hashlib
from pathlib import Path
import secrets
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from tools import android, android_signing as signing
from tests.test_android_setup import _android_build_metadata, _write_test_apk
from tests.test_android_share_manifest import manifest


def release_manifest():
    root, app, activity = manifest()
    root.attrib.update({
        "package": "io.github.gaumeloth.moontransfer",
        signing.ANDROID + "versionCode": "2",
        signing.ANDROID + "versionName": "0.1.0-test",
    })
    ET.SubElement(root, "uses-sdk", {
        signing.ANDROID + "minSdkVersion": "24",
        signing.ANDROID + "targetSdkVersion": "36",
    })
    return root, app, activity


class AndroidSigningTests(unittest.TestCase):
    def test_sdk_discovery_supports_buildozer_and_modern_layouts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "tools/bin/apkanalyzer"
            legacy.parent.mkdir(parents=True)
            legacy.touch(mode=0o700)
            with patch.dict(os.environ, {"ANDROID_HOME": str(root)}, clear=True), \
                    patch.object(signing.Path, "home", return_value=root / "home"), \
                    patch.object(signing.shutil, "which", return_value=None):
                self.assertEqual(signing.sdk_tool("apkanalyzer"), str(legacy))
                modern = root / "cmdline-tools/latest/bin/apkanalyzer"
                modern.parent.mkdir(parents=True)
                modern.touch(mode=0o700)
                self.assertEqual(signing.sdk_tool("apkanalyzer"), str(modern))
                for version in ("9.0.0", "37.0.0"):
                    tool = root / f"build-tools/{version}/apksigner"
                    tool.parent.mkdir(parents=True)
                    tool.touch(mode=0o700)
                self.assertEqual(signing.sdk_tool("apksigner"), str(root / "build-tools/37.0.0/apksigner"))

    def test_release_version_code_bounds(self):
        for value in (None, True, 0, 1, -1, 2_100_000_001, "2", 2.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                signing.validate_version_code(value)
        self.assertEqual(signing.validate_version_code(2), 2)
        self.assertEqual(signing.validate_version_code(2_100_000_000), 2_100_000_000)

    def test_certificate_fingerprint(self):
        self.assertEqual(signing.certificate_digest(":".join(["AB"] * 32)), "ab" * 32)
        for value in ("", "ab" * 31, "gg" * 32):
            with self.assertRaises(ValueError):
                signing.certificate_digest(value)

    def test_release_command_and_environment_do_not_enable_gradle_signing(self):
        self.assertEqual(
            android.buildozer_apk_command("buildozer", profile="ci", release_unsigned=True),
            ["buildozer", "--profile", "ci", "--verbose", "android", "release"],
        )
        with patch.dict(os.environ, {
            "P4A_RELEASE_KEYSTORE": "/secret/key", "P4A_RELEASE_KEYSTORE_PASSWD": "secret",
            "MOONTRANSFER_ANDROID_STORE_PASSWORD": "secret",
            "MOONTRANSFER_ANDROID_KEYSTORE_BASE64": "secret",
            "APP_ANDROID_NUMERIC_VERSION": "999", "PATH": "/bin",
        }, clear=True):
            env = android.android_build_environment(version_code=12)
            self.assertFalse(any(key.startswith(("P4A_RELEASE_", signing.PREFIX)) for key in env))
            self.assertEqual(env["APP_ANDROID_NUMERIC_VERSION"], "12")
            self.assertEqual(env["APP_ANDROID_RELEASE_ARTIFACT"], "apk")
            self.assertEqual(android.android_build_environment()["APP_ANDROID_NUMERIC_VERSION"], "1")

    def test_missing_version_code_fails_before_build(self):
        with patch.object(android, "print_environment_report") as report:
            with self.assertRaises(ValueError):
                android.build_apk(release_unsigned=True)
            report.assert_not_called()

    def test_unsigned_release_packaging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = _android_build_metadata()
            apk = root / f"moontransfer-{metadata.version}-arm64-v8a-release-unsigned.apk"
            _write_test_apk(apk, metadata=metadata)
            output = android.package_apk(metadata, dist_dir=root, release_dir=root / "release", release_unsigned=True)
            self.assertEqual(output.name, f"MoonTransfer-{metadata.version}-android-arm64-release-unsigned.apk")
            self.assertEqual(output.read_bytes(), apk.read_bytes())

    def test_release_manifest_accepts_only_expected_non_debuggable_build(self):
        root, _, _ = release_manifest()
        signing.validate_release_manifest(ET.tostring(root, encoding="unicode"), version="0.1.0-test", version_code=2)
        for node_name, attribute, value in (
            ("application", "debuggable", "true"), ("application", "testOnly", "true"),
            ("uses-sdk", "targetSdkVersion", "35"), ("uses-sdk", "minSdkVersion", "21"),
            (None, "versionName", "0.1.0-other"), (None, "versionCode", "1"),
        ):
            with self.subTest(attribute=attribute):
                root, _, _ = release_manifest()
                node = root if node_name is None else root.find(node_name)
                node.set(signing.ANDROID + attribute, value)
                with self.assertRaises(RuntimeError):
                    signing.validate_release_manifest(ET.tostring(root, encoding="unicode"), version="0.1.0-test", version_code=2)

    def test_signature_requires_one_expected_signer(self):
        with patch.object(signing, "sdk_tool", return_value="apksigner"):
            for digests, accepted in ((["ab" * 32], True), (["cd" * 32], False), ([], False), (["ab" * 32] * 2, False)):
                output = (f"Number of signers: {len(digests)}\n" + "\n".join(
                    f"Signer #{i} certificate SHA-256 digest: {d}" for i, d in enumerate(digests, 1)
                )).encode()
                with self.subTest(digests=digests), patch.object(signing, "run_tool", return_value=output):
                    if accepted:
                        signing.verify_signature(Path("app.apk"), "ab" * 32)
                    else:
                        with self.assertRaises(RuntimeError):
                            signing.verify_signature(Path("app.apk"), "ab" * 32)

    def test_build_tools_37_scheme_labels_and_mixed_certificates(self):
        with patch.object(signing, "sdk_tool", return_value="apksigner"):
            for second_digest, accepted in (("ab" * 32, True), ("cd" * 32, False)):
                output = (
                    "Number of signers: 1\n"
                    f"V3.0 Signer: certificate SHA-256 digest: {'ab' * 32}\n"
                    f"V3.1 Signer: certificate SHA-256 digest: {second_digest}\n"
                ).encode()
                with patch.object(signing, "run_tool", return_value=output):
                    if accepted:
                        signing.verify_signature(Path("app.apk"), "ab" * 32)
                    else:
                        with self.assertRaises(RuntimeError):
                            signing.verify_signature(Path("app.apk"), "ab" * 32)

    def test_signer_errors_do_not_expose_tool_output(self):
        with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"secret", b"password")):
            with self.assertRaises(RuntimeError) as error:
                signing.run_tool(["keytool"])
            self.assertNotIn("secret", str(error.exception))
            self.assertNotIn("password", str(error.exception))

    def test_keys_in_checkout_are_rejected(self):
        with self.assertRaises(ValueError):
            signing.signing_environment(android.ROOT / "key.p12", "moontransfer")

    def test_noninteractive_signing_requires_passwords(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "key.p12"
            key.touch()
            with patch.dict(os.environ, {}, clear=True), patch.object(signing.sys.stdin, "isatty", return_value=False):
                with self.assertRaises(ValueError):
                    signing.signing_environment(key, "moontransfer")

    def test_signing_order_password_arguments_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "app.apk"
            commands = []

            def tool(command, **kwargs):
                commands.append((command, kwargs))
                if "--out" in command:
                    Path(command[command.index("--out") + 1]).write_bytes(b"signed")
                return b""

            with patch.object(signing, "validate_apk"), patch.object(signing, "validate_release_manifest"), \
                    patch.object(signing, "create_build_metadata"), patch.object(signing, "verify_signature") as verify, \
                    patch.object(signing, "sdk_tool", side_effect=lambda name: name), \
                    patch.object(signing, "signing_environment", return_value={"secret": "value"}), \
                    patch.object(signing, "run_tool", side_effect=tool):
                args = dict(keystore=root / "key.p12", alias="moontransfer", expected_sha256="ab" * 32,
                            version="0.1.0-test", commit="a" * 40, version_code=2)
                signing.sign_apk(root / "unsigned.apk", output, **args)
                self.assertEqual(output.read_bytes(), b"signed")
                self.assertEqual([command[0] for command, _ in commands], ["apkanalyzer", "zipalign", "apksigner", "zipalign"])
                sign_command = commands[2][0]
                self.assertIn("env:MOONTRANSFER_ANDROID_STORE_PASSWORD", sign_command)
                self.assertNotIn("value", sign_command)
                verify.assert_called_once()
                with self.assertRaises(ValueError):
                    signing.sign_apk(root / "unsigned.apk", output, **args)
                self.assertFalse(list(root.glob(".android-sign-*")))

    def test_invalid_signature_never_publishes_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(signing, "validate_apk"), patch.object(signing, "validate_release_manifest"), \
                    patch.object(signing, "create_build_metadata"), \
                    patch.object(signing, "verify_signature", side_effect=RuntimeError("Wrong certificate")), \
                    patch.object(signing, "sdk_tool", side_effect=lambda name: name), \
                    patch.object(signing, "signing_environment", return_value={}), \
                    patch.object(signing, "run_tool", return_value=b""):
                with self.assertRaisesRegex(RuntimeError, "Wrong certificate"):
                    signing.sign_apk(root / "unsigned.apk", root / "signed.apk", keystore=root / "key.p12",
                                     alias="moontransfer", expected_sha256="ab" * 32, version="0.1.0-test",
                                     commit="a" * 40, version_code=2)
                self.assertFalse((root / "signed.apk").exists())
                self.assertFalse(list(root.glob(".android-sign-*")))


@unittest.skipUnless(os.environ.get("MOONTRANSFER_SIGNING_TEST_APK"), "opt-in real Android SDK signing test")
class AndroidSigningIntegrationTests(unittest.TestCase):
    def test_temporary_key_local_and_ci_round_trip(self):
        apk = Path(os.environ["MOONTRANSFER_SIGNING_TEST_APK"]).absolute()
        version = os.environ["MOONTRANSFER_SIGNING_TEST_VERSION"]
        commit = os.environ["MOONTRANSFER_SIGNING_TEST_COMMIT"]
        version_code = int(os.environ["MOONTRANSFER_SIGNING_TEST_VERSION_CODE"])
        with tempfile.TemporaryDirectory(prefix="moontransfer-signing-test-") as directory:
            root = Path(directory)
            key = root / "local.p12"
            password = secrets.token_urlsafe(32)
            with patch.object(signing.sys.stdin, "isatty", return_value=True), \
                    patch.object(signing.getpass, "getpass", return_value=password):
                signing.init_keystore(key, "moontransfer")
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                signing.init_keystore(key, "moontransfer")
            environment = {
                signing.PREFIX + "STORE_PASSWORD": password,
                signing.PREFIX + "KEY_PASSWORD": password,
            }
            with patch.dict(os.environ, environment):
                certificate = signing.run_tool([
                    "keytool", "-exportcert", "-keystore", str(key), "-alias", "moontransfer",
                    "-storepass:env", signing.PREFIX + "STORE_PASSWORD",
                ])
                fingerprint = hashlib.sha256(certificate).hexdigest()
                ci_key = root / "ci.p12"
                ci_key.write_bytes(base64.b64decode(base64.b64encode(key.read_bytes()), validate=True))
                for label, signing_key in (("local", key), ("ci", ci_key)):
                    target = root / f"{label}.apk"
                    signing.sign_apk(apk, target, keystore=signing_key, alias="moontransfer",
                                     expected_sha256=fingerprint, version=version, commit=commit,
                                     version_code=version_code)
                    signing.verify_signature(target, fingerprint)
                with self.assertRaisesRegex(RuntimeError, "certificate"):
                    signing.sign_apk(apk, root / "wrong.apk", keystore=key, alias="moontransfer",
                                     expected_sha256="00" * 32, version=version, commit=commit,
                                     version_code=version_code)
                self.assertFalse((root / "wrong.apk").exists())


if __name__ == "__main__":
    unittest.main()

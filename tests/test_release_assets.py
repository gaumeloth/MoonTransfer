from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.android import release_version_code
from tools.release_assets import ASSET_SUFFIXES, version_from_tag, write_checksums


class ReleaseAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.version = "0.1.0-alpha.99"
        self.names = [f"MoonTransfer-{self.version}-{suffix}" for suffix in ASSET_SUFFIXES]
        for name in self.names:
            (self.directory / name).write_bytes(name.encode("ascii"))

    def checksums(self):
        return write_checksums(self.directory, tag=f"v{self.version}", project_version="0.1.0")

    def test_all_five_packages_have_reproducible_checksums(self):
        path = self.checksums()
        expected = "".join(
            f"{hashlib.sha256(name.encode('ascii')).hexdigest()}  {name}\n"
            for name in sorted(self.names)
        )
        self.assertEqual(path.read_text(), expected)
        self.checksums()
        self.assertEqual(path.read_text(), expected)

    def test_missing_android_or_desktop_blocks_draft_checksums(self):
        for name in self.names:
            with self.subTest(name=name):
                path = self.directory / name
                data = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(ValueError, "missing"):
                    self.checksums()
                self.assertFalse((self.directory / "SHA256SUMS").exists())
                path.write_bytes(data)

    def test_debug_unsigned_and_wrong_version_apks_are_rejected(self):
        for name in (
            f"MoonTransfer-{self.version}-android-arm64-debug.apk",
            f"MoonTransfer-{self.version}-android-arm64-release-unsigned.apk",
            "MoonTransfer-0.1.0-alpha.98-android-arm64.apk",
        ):
            with self.subTest(name=name):
                path = self.directory / name
                path.touch()
                with self.assertRaisesRegex(ValueError, "unexpected"):
                    self.checksums()
                path.unlink()

    def test_empty_directory_and_symbolic_assets_are_rejected(self):
        path = self.directory / self.names[0]
        path.write_bytes(b"")
        with self.assertRaises(ValueError):
            self.checksums()
        path.unlink()
        path.mkdir()
        with self.assertRaises(ValueError):
            self.checksums()
        path.rmdir()
        try:
            path.symlink_to(self.directory / self.names[1])
        except OSError:
            self.skipTest("Creating symlinks is unavailable on this host")
        with self.assertRaises(ValueError):
            self.checksums()

    def test_unsafe_checksum_path_is_not_overwritten(self):
        destination = self.directory / "SHA256SUMS"
        destination.mkdir()
        with self.assertRaises(ValueError):
            self.checksums()

    def test_invalid_tag_and_project_mismatch(self):
        for tag in ("v0.1.0", "v0.1.0-dev.1", "v0.2.0-alpha.1", "v0.1.0-alpha.1/../bad", "v0.1.0-rc.1\n"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                version_from_tag(tag, project_version="0.1.0")
        for stage in ("alpha", "beta", "rc"):
            self.assertEqual(version_from_tag(f"v0.1.0-{stage}.1", project_version="0.1.0"), f"0.1.0-{stage}.1")

    def test_versioned_android_code_is_validated(self):
        path = self.directory / "release.toml"
        for setting in ('version_code = 1', 'version_code = true', 'version_code = "2"', 'unrelated = 2'):
            path.write_text(setting)
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                release_version_code(path)
        path.write_text("version_code = 2")
        self.assertEqual(release_version_code(path), 2)


if __name__ == "__main__":
    unittest.main()

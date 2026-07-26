from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import fetch_croc


class FetchCrocConfigTests(unittest.TestCase):
    def test_read_croc_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            pyproject.write_text(
                """
[tool.moontransfer.croc]
version = "v10.4.13"

[tool.moontransfer.croc.hashes]
"croc_v10.4.13_Linux-64bit.tar.gz" = "sha256:656125605320b424ca37594cb5caf3860a6c9fd7081b9ba385f5c4548838cfb3"
""".strip(),
                encoding="utf-8",
            )

            version, hashes = fetch_croc.read_croc_config(pyproject)

        self.assertEqual(version, "10.4.13")
        self.assertEqual(
            hashes["croc_v10.4.13_Linux-64bit.tar.gz"],
            "656125605320b424ca37594cb5caf3860a6c9fd7081b9ba385f5c4548838cfb3",
        )

    def test_expected_hash_for_asset_requires_known_asset(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Missing pinned SHA-256"):
            fetch_croc.expected_hash_for_asset("missing.tar.gz", {})


class FetchCrocAssetTests(unittest.TestCase):
    def test_pick_asset_linux_x86_64(self) -> None:
        self.assertEqual(
            fetch_croc.pick_asset("10.4.13", system="Linux", machine="x86_64"),
            "croc_v10.4.13_Linux-64bit.tar.gz",
        )

    def test_pick_asset_linux_arm64(self) -> None:
        self.assertEqual(
            fetch_croc.pick_asset("10.4.13", system="Linux", machine="aarch64"),
            "croc_v10.4.13_Linux-ARM64.tar.gz",
        )

    def test_pick_asset_macos_x86_64(self) -> None:
        self.assertEqual(
            fetch_croc.pick_asset("10.4.13", system="Darwin", machine="x86_64"),
            "croc_v10.4.13_macOS-64bit.tar.gz",
        )

    def test_pick_asset_macos_arm64(self) -> None:
        self.assertEqual(
            fetch_croc.pick_asset("10.4.13", system="Darwin", machine="arm64"),
            "croc_v10.4.13_macOS-ARM64.tar.gz",
        )

    def test_pick_asset_windows_x86_64(self) -> None:
        self.assertEqual(
            fetch_croc.pick_asset("10.4.13", system="Windows", machine="AMD64"),
            "croc_v10.4.13_Windows-64bit.zip",
        )

    def test_pick_asset_windows_arm64(self) -> None:
        self.assertEqual(
            fetch_croc.pick_asset("10.4.13", system="Windows", machine="ARM64"),
            "croc_v10.4.13_Windows-ARM64.zip",
        )

    def test_pick_asset_rejects_unsupported_platform(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unsupported platform"):
            fetch_croc.pick_asset("10.4.13", system="Linux", machine="i686")

    def test_asset_download_url_uses_exact_version(self) -> None:
        self.assertEqual(
            fetch_croc.asset_download_url(
                "v10.4.13",
                "croc_v10.4.13_Linux-64bit.tar.gz",
            ),
            "https://github.com/schollz/croc/releases/download/"
            "v10.4.13/croc_v10.4.13_Linux-64bit.tar.gz",
        )


class FetchCrocChecksumTests(unittest.TestCase):
    def test_parse_checksum_normalizes_sha256(self) -> None:
        checksums = fetch_croc.parse_checksum(
            "ABCDEFabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234  asset.zip"
        )

        self.assertEqual(
            checksums["asset.zip"],
            "abcdefabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234",
        )

    def test_verify_archive_accepts_expected_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "asset.zip"
            archive.write_bytes(b"data")
            expected = fetch_croc.sha256_file(archive)

            fetch_croc.verify_archive("asset.zip", archive, f"sha256:{expected}")

    def test_verify_archive_rejects_wrong_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "asset.zip"
            archive.write_bytes(b"data")

            with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch"):
                fetch_croc.verify_archive("asset.zip", archive, "0" * 64)


class FetchCrocExtractionTests(unittest.TestCase):
    def test_safe_extract_tar_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tar_path = Path(tmp) / "bad.tar.gz"
            with tarfile.open(tar_path, "w:gz") as tar:
                payload = b"bad"
                info = tarfile.TarInfo("../bad")
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))

            with tarfile.open(tar_path, "r:gz") as tar:
                with self.assertRaisesRegex(RuntimeError, "Path traversal"):
                    fetch_croc.safe_extract_tar(tar, Path(tmp) / "out")

    def test_safe_extract_tar_rejects_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tar_path = Path(tmp) / "bad.tar.gz"
            with tarfile.open(tar_path, "w:gz") as tar:
                info = tarfile.TarInfo("link")
                info.type = tarfile.SYMTYPE
                info.linkname = "/tmp/target"
                tar.addfile(info)

            with tarfile.open(tar_path, "r:gz") as tar:
                with self.assertRaisesRegex(RuntimeError, "Links are not supported"):
                    fetch_croc.safe_extract_tar(tar, Path(tmp) / "out")

    def test_safe_extract_tar_rejects_special_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tar_path = Path(tmp) / "bad.tar.gz"
            with tarfile.open(tar_path, "w:gz") as tar:
                info = tarfile.TarInfo("pipe")
                info.type = tarfile.FIFOTYPE
                tar.addfile(info)

            with tarfile.open(tar_path, "r:gz") as tar:
                with self.assertRaisesRegex(RuntimeError, "Special files"):
                    fetch_croc.safe_extract_tar(tar, Path(tmp) / "out")


class FetchCrocInstallTests(unittest.TestCase):
    def test_matching_version_marker_still_reinstalls_verified_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = "croc-test.tar.gz"
            archive = root / ".cache" / asset
            archive.parent.mkdir()
            archive.write_bytes(b"verified archive")
            expected_hash = fetch_croc.sha256_file(archive)

            pyproject = root / "pyproject.toml"
            pyproject.write_text(
                (
                    "[tool.moontransfer.croc]\n"
                    'version = "10.4.13"\n\n'
                    "[tool.moontransfer.croc.hashes]\n"
                    f'"{asset}" = "sha256:{expected_hash}"\n'
                ),
                encoding="utf-8",
            )

            executable = "croc.exe" if fetch_croc.os.name == "nt" else "croc"
            destination = root / "third_party" / "croc" / executable
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"untrusted preexisting binary")
            (destination.parent / "VERSION").write_text(
                "10.4.13\n",
                encoding="utf-8",
            )

            def fake_extract(
                _asset: str,
                _archive: Path,
                extract_dir: Path,
            ) -> None:
                extract_dir.mkdir(parents=True, exist_ok=True)
                (extract_dir / executable).write_bytes(b"verified binary")

            fake_module_file = root / "tools" / "fetch_croc.py"
            with (
                mock.patch.object(fetch_croc, "__file__", str(fake_module_file)),
                mock.patch.object(fetch_croc, "pick_asset", return_value=asset),
                mock.patch.object(fetch_croc, "extract_archive", side_effect=fake_extract),
            ):
                fetch_croc.main([])

            self.assertEqual(destination.read_bytes(), b"verified binary")


if __name__ == "__main__":
    unittest.main()

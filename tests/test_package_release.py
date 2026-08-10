from __future__ import annotations

import os
import stat
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tools import package_release


class PackageReleaseTests(unittest.TestCase):
    def test_normalize_architecture(self) -> None:
        self.assertEqual(package_release.normalize_architecture("AMD64"), "x86_64")
        self.assertEqual(package_release.normalize_architecture("aarch64"), "arm64")

    def test_validate_version_strips_tag_prefix(self) -> None:
        self.assertEqual(
            package_release.validate_version("v0.1.0-alpha.1"),
            "0.1.0-alpha.1",
        )

    def test_validate_version_rejects_path_components(self) -> None:
        with self.assertRaises(ValueError):
            package_release.validate_version("../0.1.0")

    def test_validate_host_rejects_a_mismatched_target(self) -> None:
        with self.assertRaises(RuntimeError):
            package_release.validate_host(
                package_release.TARGETS["windows-x86_64"],
                system="Linux",
                machine="x86_64",
            )

    def test_read_croc_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            pyproject.write_text(
                '[tool.moontransfer.croc]\nversion = "10.4.13"\n',
                encoding="utf-8",
            )
            self.assertEqual(
                package_release.read_croc_version(pyproject),
                "10.4.13",
            )

    def test_validate_package_version_matches_project_base_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            pyproject.write_text(
                '[project]\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            self.assertEqual(
                package_release.validate_package_version(
                    pyproject,
                    "0.1.0-alpha.1",
                ),
                "0.1.0-alpha.1",
            )

    def test_validate_package_version_rejects_a_different_project_version(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            pyproject.write_text(
                '[project]\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                package_release.validate_package_version(
                    pyproject,
                    "0.2.0-alpha.1",
                )

    def test_verify_croc_version_rejects_unexpected_output(self) -> None:
        result = mock.Mock(returncode=0, stdout="croc version v99.0.0", stderr="")
        with (
            mock.patch.object(package_release.subprocess, "run", return_value=result),
            self.assertRaises(RuntimeError),
        ):
            package_release.verify_croc_version(Path("/fake/croc"), "10.4.13")

    def test_verify_croc_version_accepts_supported_output_formats(self) -> None:
        for output in ("croc version v10.4.13", "croc version 10.4.13"):
            with (
                self.subTest(output=output),
                mock.patch.object(
                    package_release.subprocess,
                    "run",
                    return_value=mock.Mock(
                        returncode=0,
                        stdout=output,
                        stderr="",
                    ),
                ),
            ):
                package_release.verify_croc_version(
                    Path("/fake/croc"),
                    "10.4.13",
                )

    def test_validate_linux_bundle_rejects_incomplete_qt_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = package_release.TARGETS["linux-x86_64"]
            bundle = self._create_bundle(root, target)
            missing = "libxkbcommon-x11.so.0"
            (bundle / "_internal" / missing).unlink()

            with self.assertRaisesRegex(FileNotFoundError, missing):
                package_release.validate_bundle(
                    root,
                    target,
                    verify_croc=False,
                )

    def test_create_linux_package_preserves_executable_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._create_bundle(
                root,
                package_release.TARGETS["linux-x86_64"],
            )
            package = package_release.create_release_package(
                root,
                package_release.TARGETS["linux-x86_64"],
                "0.1.0-alpha.1",
                verify_croc=False,
            )

            with tarfile.open(package, "r:gz") as archive:
                executable = archive.getmember(
                    "MoonTransfer-0.1.0-alpha.1/MoonTransfer"
                )
                if os.name != "nt":
                    self.assertTrue(executable.mode & stat.S_IXUSR)
                self.assertIn(
                    "MoonTransfer-0.1.0-alpha.1/_internal/croc",
                    archive.getnames(),
                )
                self.assertIn(
                    "MoonTransfer-0.1.0-alpha.1/LICENSE",
                    archive.getnames(),
                )
            self.assertEqual(bundle.name, "MoonTransfer")

    def test_create_windows_package_contains_the_complete_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_bundle(
                root,
                package_release.TARGETS["windows-x86_64"],
            )
            package = package_release.create_release_package(
                root,
                package_release.TARGETS["windows-x86_64"],
                "0.1.0-alpha.1",
                verify_croc=False,
            )

            with zipfile.ZipFile(package) as archive:
                self.assertIn(
                    "MoonTransfer-0.1.0-alpha.1/MoonTransfer.exe",
                    archive.namelist(),
                )
                self.assertIn(
                    "MoonTransfer-0.1.0-alpha.1/_internal/croc.exe",
                    archive.namelist(),
                )

    def test_create_macos_package_contains_the_app_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_bundle(
                root,
                package_release.TARGETS["macos-x86_64"],
            )
            package = package_release.create_release_package(
                root,
                package_release.TARGETS["macos-x86_64"],
                "0.1.0-alpha.1",
                verify_croc=False,
            )

            with tarfile.open(package, "r:gz") as archive:
                self.assertIn(
                    "MoonTransfer-0.1.0-alpha.1/"
                    "MoonTransfer.app/Contents/MacOS/MoonTransfer",
                    archive.getnames(),
                )
                self.assertIn(
                    "MoonTransfer-0.1.0-alpha.1/"
                    "MoonTransfer.app/_internal/croc",
                    archive.getnames(),
                )
                self.assertIn(
                    "MoonTransfer-0.1.0-alpha.1/LICENSE",
                    archive.getnames(),
                )

    @staticmethod
    def _create_bundle(
        root: Path,
        target: package_release.ReleaseTarget,
    ) -> Path:
        bundle = root / "dist" / target.bundle_name
        executable = bundle / target.executable_relative
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"application")
        executable.chmod(0o755)

        croc = bundle / "_internal" / target.croc_name
        croc.parent.mkdir(parents=True, exist_ok=True)
        croc.write_bytes(b"croc")
        croc.chmod(0o755)
        if target.system == "Linux":
            for name in package_release.LINUX_QT_XCB_RUNTIME_LIBRARIES:
                (bundle / "_internal" / name).write_bytes(b"library")
        (root / "pyproject.toml").write_text(
            '[project]\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        for name in package_release.RELEASE_DOCUMENT_NAMES:
            (root / name).write_text(name, encoding="utf-8")
        return bundle


if __name__ == "__main__":
    unittest.main()

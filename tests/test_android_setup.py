from __future__ import annotations

import ast
import configparser
import os
import re
import tempfile
import tomllib
import unittest
from pathlib import Path

from tools import android as android_tool
from tools import prepare_android


ROOT = Path(__file__).resolve().parents[1]


def read_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


class AndroidDependencyIsolationTests(unittest.TestCase):
    def test_android_dependencies_do_not_change_desktop_runtime(self) -> None:
        desktop = read_toml(ROOT / "pyproject.toml")
        android = read_toml(ROOT / "android" / "pyproject.toml")

        desktop_dependencies = desktop["project"]["dependencies"]
        self.assertIn("PySide6>=6.6", desktop_dependencies)
        self.assertEqual(
            desktop["project"]["scripts"]["moontransfer"],
            "moontransfer.app:main",
        )
        self.assertNotIn("kivy", " ".join(desktop_dependencies).lower())
        self.assertEqual(android["project"]["requires-python"], ">=3.13,<3.14")
        self.assertEqual(android["project"]["dependencies"], ["kivy==2.3.1"])
        self.assertIn("buildozer==1.6.0", android["dependency-groups"]["build"])
        self.assertIn("pip>=24", android["dependency-groups"]["build"])

    def test_android_project_version_matches_desktop_project(self) -> None:
        desktop = read_toml(ROOT / "pyproject.toml")
        android = read_toml(ROOT / "android" / "pyproject.toml")

        self.assertEqual(
            android["project"]["version"],
            desktop["project"]["version"],
        )


class AndroidBuildConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = configparser.ConfigParser(interpolation=None)
        loaded = self.config.read(
            ROOT / "android" / "buildozer.spec",
            encoding="utf-8",
        )
        self.assertTrue(loaded)
        self.app = self.config["app"]

    def test_build_uses_generated_sources_and_pinned_toolchain(self) -> None:
        self.assertEqual(self.app["source.dir"], "../build/android/source")
        self.assertEqual(
            self.app["requirements"],
            "python3==3.13.14,hostpython3==3.13.14,kivy==2.3.1,"
            "chardet==5.2.0,croc",
        )
        self.assertEqual(self.app["p4a.branch"], "v2026.05.09")
        self.assertEqual(self.app["android.ndk"], "28c")
        self.assertEqual(self.app["android.api"], "36")
        self.assertEqual(self.app["android.archs"], "arm64-v8a")

    def test_croc_recipe_is_pinned_and_packaged_as_a_native_executable(self) -> None:
        recipe_path = ROOT / "android" / "recipes" / "croc" / "__init__.py"
        recipe_source = recipe_path.read_text(encoding="utf-8")
        tree = ast.parse(recipe_source)
        recipe_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "CrocRecipe"
        )
        assignments = {
            target.id: ast.literal_eval(statement.value)
            for statement in recipe_class.body
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance((target := statement.targets[0]), ast.Name)
            and target.id in {"version", "url", "sha512sum", "built_libraries"}
        }

        project = read_toml(ROOT / "pyproject.toml")
        self.assertEqual(
            assignments["version"],
            project["tool"]["moontransfer"]["croc"]["version"],
        )
        self.assertEqual(
            assignments["url"],
            "https://github.com/schollz/croc/archive/refs/tags/v{version}.tar.gz",
        )
        self.assertEqual(
            assignments["sha512sum"],
            "57dd2b4b0f9adf80e07bc1112c19c6b5376add4b1f08fd91b5ff2b720c88274a"
            "a75d8a75cea0b3dfb61fc3f5285e6fbdc94f232085f29b29e814bcbd17ad72d8",
        )
        self.assertEqual(assignments["built_libraries"], {"libcroc.so": "."})
        self.assertIn('"GOOS": "android"', recipe_source)
        self.assertIn('"CGO_ENABLED": "1"', recipe_source)
        self.assertIn("with_flags_in_cc=False", recipe_source)
        self.assertIn("get_clang_exe(with_target=True)", recipe_source)

    def test_build_declares_no_broad_storage_permission(self) -> None:
        permissions = {
            permission.strip()
            for permission in self.app["android.permissions"].split(",")
        }

        self.assertEqual(permissions, {"android.permission.INTERNET"})
        self.assertFalse(
            any("STORAGE" in permission or "MANAGE_EXTERNAL" in permission for permission in permissions)
        )

    def test_android_application_id_matches_desktop_bundle_identifier(self) -> None:
        self.assertEqual(
            f'{self.app["package.domain"]}.{self.app["package.name"]}',
            "io.github.gaumeloth.moontransfer",
        )


class AndroidSourcePreparationTests(unittest.TestCase):
    def test_preparation_copies_only_qt_independent_shared_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source"
            prepared = prepare_android.prepare_android_source(
                root=ROOT,
                destination=destination,
            )

            package = prepared / "moontransfer"
            self.assertTrue((prepared / "main.py").is_file())
            self.assertTrue(
                (prepared / "moontransfer_android" / "application.py").is_file()
            )
            self.assertTrue(
                (prepared / "moontransfer_android" / "transport.py").is_file()
            )
            self.assertTrue(
                (prepared / "moontransfer_android" / "storage.py").is_file()
            )
            self.assertTrue(
                (prepared / "moontransfer_android" / "sender.py").is_file()
            )
            self.assertTrue(
                (
                    prepared
                    / "moontransfer_android"
                    / "licenses"
                    / "croc.txt"
                ).is_file()
            )
            for filename in prepare_android.SHARED_MODULES:
                self.assertTrue((package / filename).is_file(), filename)
            for filename in (
                "app.py",
                "desktop.py",
                "runner.py",
                "tasks.py",
                "transfer.py",
                "widgets.py",
            ):
                self.assertFalse((package / filename).exists(), filename)

            for source in prepared.rglob("*.py"):
                self.assertNotIn("PySide6", source.read_text(encoding="utf-8"))

    def test_preparation_uses_project_version_and_excludes_source_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source"
            prepared = prepare_android.prepare_android_source(
                root=ROOT,
                destination=destination,
            )

            main_source = (prepared / "main.py").read_text(encoding="utf-8")
            project_version = read_toml(ROOT / "pyproject.toml")["project"][
                "version"
            ]
            self.assertIn(f'__version__ = "{project_version}"', main_source)

            config = configparser.ConfigParser(interpolation=None)
            config.read(ROOT / "android" / "buildozer.spec", encoding="utf-8")
            version_match = re.search(
                config["app"]["version.regex"],
                main_source,
            )
            self.assertIsNotNone(version_match)
            self.assertEqual(version_match.group(1), project_version)

            self.assertTrue(
                (
                    prepared
                    / "moontransfer"
                    / "assets"
                    / "icons"
                    / "moontransfer-icon.png"
                ).is_file()
            )
            self.assertFalse(any(prepared.rglob("*.xcf")))

    def test_preparation_replaces_stale_generated_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source"
            prepare_android.prepare_android_source(
                root=ROOT,
                destination=destination,
            )
            stale = destination / "stale.txt"
            stale.write_text("stale", encoding="utf-8")

            prepare_android.prepare_android_source(
                root=ROOT,
                destination=destination,
            )

            self.assertFalse(stale.exists())

    @unittest.skipIf(os.name == "nt", "Creating symlinks is restricted on Windows.")
    def test_preparation_refuses_to_replace_a_symbolic_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            target = temporary / "target"
            target.mkdir()
            destination = temporary / "source"
            destination.symlink_to(target, target_is_directory=True)

            with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                prepare_android.prepare_android_source(
                    root=ROOT,
                    destination=destination,
                )


class AndroidDoctorTests(unittest.TestCase):
    def test_required_commands_are_platform_specific(self) -> None:
        linux = android_tool.required_build_commands("Linux")
        macos = android_tool.required_build_commands("Darwin")

        self.assertIn("gcc", linux)
        self.assertIn("go", linux)
        self.assertNotIn("clang", linux)
        self.assertIn("clang", macos)
        self.assertNotIn("gcc", macos)

    def test_missing_command_detection_is_deterministic(self) -> None:
        available = {"git": "/usr/bin/git"}

        missing = android_tool.find_missing_commands(
            ("git", "javac", "cargo"),
            which=available.get,
        )

        self.assertEqual(missing, ("javac", "cargo"))

    def test_go_version_parser_accepts_current_version_output(self) -> None:
        self.assertEqual(
            android_tool.parse_go_version(
                "go version go1.26.5-X:nodwarf5 linux/amd64"
            ),
            (1, 26),
        )

    def test_go_version_parser_rejects_unrelated_output(self) -> None:
        self.assertIsNone(android_tool.parse_go_version("Python 3.13.11"))

    def test_missing_python_module_detection_is_deterministic(self) -> None:
        available = {"pip": object()}

        missing = android_tool.find_missing_python_modules(
            ("pip", "build"),
            find_spec=available.get,
        )

        self.assertEqual(missing, ("build",))


if __name__ == "__main__":
    unittest.main()

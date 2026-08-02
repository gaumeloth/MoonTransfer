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

        self.assertEqual(
            permissions,
            {
                "android.permission.INTERNET",
                "android.permission.FOREGROUND_SERVICE",
                "android.permission.FOREGROUND_SERVICE_DATA_SYNC",
                "android.permission.POST_NOTIFICATIONS",
            },
        )
        self.assertFalse(
            any(
                "STORAGE" in permission or "MANAGE_EXTERNAL" in permission
                for permission in permissions
            )
        )

    def test_transfer_runs_in_a_data_sync_foreground_service(self) -> None:
        self.assertEqual(
            self.app["services"],
            "Transfer:moontransfer_android/service.py:foreground:sticky:"
            "foregroundServiceType=dataSync",
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
                (prepared / "moontransfer_android" / "receiver.py").is_file()
            )
            for filename in (
                "android_runtime.py",
                "service.py",
                "service_client.py",
                "service_protocol.py",
                "transfer_service.py",
            ):
                self.assertTrue(
                    (prepared / "moontransfer_android" / filename).is_file(),
                    filename,
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

    def test_preparation_uses_project_version_and_excludes_artifacts(
        self,
    ) -> None:
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


class AndroidApplicationLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = (
            ROOT
            / "android"
            / "app"
            / "moontransfer_android"
            / "application.py"
        ).read_text(encoding="utf-8")
        cls.application = next(
            node
            for node in ast.parse(source).body
            if isinstance(node, ast.ClassDef)
            and node.name == "MoonTransferAndroidApp"
        )

    @classmethod
    def method(cls, name: str) -> ast.FunctionDef:
        return next(
            node
            for node in cls.application.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )

    def test_service_release_has_an_explicit_control_refresh(self) -> None:
        release = self.method("_release_service")
        finish = self.method("_finish_service_release")
        resume = self.method("on_resume")

        scheduled_callbacks = {
            ast.unparse(call.args[0])
            for call in ast.walk(release)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "schedule_once"
            and call.args
        }
        finish_calls = {
            ast.unparse(call.func)
            for call in ast.walk(finish)
            if isinstance(call, ast.Call)
        }
        resume_calls = {
            ast.unparse(call.func)
            for call in ast.walk(resume)
            if isinstance(call, ast.Call)
        }

        self.assertIn("self._finish_service_release", scheduled_callbacks)
        self.assertIn("self._update_controls", finish_calls)
        self.assertIn("self._update_controls", resume_calls)

    def test_release_guard_only_blocks_starting_the_next_service(self) -> None:
        controls_source = ast.unparse(self.method("_update_controls"))

        self.assertIn(
            "transfer_active = send_active or receive_active",
            controls_source,
        )
        self.assertIn(
            "service_start_blocked = transfer_active or service_releasing",
            controls_source,
        )

    def test_unresponsive_service_is_stopped_cleaned_and_released(self) -> None:
        poll_source = ast.unparse(self.method("_poll_transfer_service"))
        recovery_source = ast.unparse(
            self.method("_handle_unresponsive_service")
        )

        self.assertIn("self._service_heartbeat.timed_out(snapshot)", poll_source)
        self.assertIn("client.stop()", recovery_source)
        self.assertIn("self._release_service(client)", recovery_source)
        self.assertIn("cleanup_staging_parent", recovery_source)


class AndroidNotificationSourceTests(unittest.TestCase):
    def test_notifications_have_distinct_ids_and_private_content(self) -> None:
        source = (
            ROOT
            / "android"
            / "app"
            / "moontransfer_android"
            / "android_runtime.py"
        ).read_text(encoding="utf-8")
        assignments = {
            target.id: ast.literal_eval(statement.value)
            for statement in ast.parse(source).body
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance((target := statement.targets[0]), ast.Name)
            and target.id
            in {"TRANSFER_SERVICE_ID", "TRANSFER_RESULT_NOTIFICATION_ID"}
        }

        self.assertNotEqual(
            assignments["TRANSFER_SERVICE_ID"],
            assignments["TRANSFER_RESULT_NOTIFICATION_ID"],
        )
        self.assertIn("setProgress", source)
        self.assertIn("setPublicVersion", source)
        self.assertIn("VISIBILITY_PRIVATE", source)
        self.assertIn(
            'autoclass("android.app.Notification$Builder")',
            source,
        )
        self.assertNotIn("notification_class.Builder", source)


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

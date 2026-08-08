from __future__ import annotations

import ast
import configparser
import json
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
            "fc316adff9c977d38031d49a87f9e6df2da1596e2279d8890cfc81d5c63f2f57"
            "ed082117b5e26eba8b9f6b7c80355746563be11b8a460ef4ae089666f3030b26",
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
        self.assertEqual(self.app["android.add_src"], "java")
        self.assertEqual(
            self.app["android.service_class_name"],
            "io.github.gaumeloth.moontransfer.MoonTransferPythonService",
        )

    def test_service_handles_android_timeout_and_invalid_sticky_restart(self) -> None:
        java_root = (
            ROOT
            / "android"
            / "java"
            / "io"
            / "github"
            / "gaumeloth"
            / "moontransfer"
        )
        service = (java_root / "MoonTransferPythonService.java").read_text(
            encoding="utf-8"
        )
        control = (java_root / "TransferControl.java").read_text(
            encoding="utf-8"
        )
        action = (java_root / "TransferNotificationAction.java").read_text(
            encoding="utf-8"
        )

        self.assertIn("void onTimeout(int startId, int fgsType)", service)
        self.assertIn("TransferControl.requestCancel", service)
        self.assertIn("stopSelf(startId)", service)
        self.assertIn("if (intent == null)", service)
        self.assertIn("return START_NOT_STICKY", service)
        self.assertIn("ACTION_CANCEL_TRANSFER.equals(", service)
        self.assertIn("requestedSession.equals(activeSessionId)", service)
        self.assertIn('command.put("command", "cancel")', control)
        self.assertIn("getCanonicalFile()", control)
        self.assertIn("public static void addCancelAction", action)

    def test_service_uses_visible_moontransfer_notification_channel(self) -> None:
        java_root = (
            ROOT
            / "android"
            / "java"
            / "io"
            / "github"
            / "gaumeloth"
            / "moontransfer"
        )
        service = (java_root / "MoonTransferPythonService.java").read_text(
            encoding="utf-8"
        )
        runtime_path = (
            ROOT
            / "android"
            / "app"
            / "moontransfer_android"
            / "android_runtime.py"
        )
        runtime_source = runtime_path.read_text(encoding="utf-8")
        runtime_tree = ast.parse(runtime_source)
        runtime_channel = next(
            ast.literal_eval(statement.value)
            for statement in runtime_tree.body
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == "TRANSFER_NOTIFICATION_CHANNEL"
        )
        java_channel = re.search(
            r'NOTIFICATION_CHANNEL_ID\s*=\s*"([^"]+)"',
            service,
        )

        self.assertIsNotNone(java_channel)
        assert java_channel is not None
        self.assertEqual(java_channel.group(1), runtime_channel)
        self.assertNotEqual(runtime_channel, "org.kivy.p4a1")
        self.assertIn("protected void doStartForeground(Bundle extras)", service)
        self.assertIn("NotificationManager.IMPORTANCE_LOW", service)
        self.assertNotIn("NotificationManager.IMPORTANCE_NONE", service)
        self.assertIn("startForeground(getServiceId(), notification)", service)

    def test_android_application_id_matches_desktop_bundle_identifier(self) -> None:
        self.assertEqual(
            f'{self.app["package.domain"]}.{self.app["package.name"]}',
            "io.github.gaumeloth.moontransfer",
        )


class AndroidCrocBuildCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.build_root = self.root / "platform" / "build-arm64-v8a"
        self.recipe_path = self.root / "recipe.py"
        self.marker_path = self.root / "recipe.sha256"
        self.recipe_path.write_text('version = "11.0.1"\n', encoding="ascii")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _create_cached_directories(self) -> tuple[Path, ...]:
        paths = tuple(
            self.build_root / relative
            for relative in android_tool.CROC_BUILD_CACHE_PATHS
        )
        for path in paths:
            path.mkdir(parents=True)
            (path / "stale").write_text("old", encoding="ascii")
        return paths

    def test_stale_recipe_fingerprint_removes_native_cache(self) -> None:
        cached_paths = self._create_cached_directories()
        self.marker_path.write_text("old-fingerprint\n", encoding="ascii")

        fingerprint, removed = android_tool.invalidate_stale_croc_build_cache(
            build_root=self.build_root,
            recipe_path=self.recipe_path,
            marker_path=self.marker_path,
        )

        self.assertTrue(removed)
        self.assertTrue(all(not path.exists() for path in cached_paths))
        self.assertEqual(
            fingerprint,
            android_tool.croc_recipe_fingerprint(self.recipe_path),
        )

    def test_matching_recipe_fingerprint_preserves_native_cache(self) -> None:
        cached_paths = self._create_cached_directories()
        fingerprint = android_tool.croc_recipe_fingerprint(self.recipe_path)
        android_tool.record_croc_recipe_fingerprint(
            fingerprint,
            self.marker_path,
        )

        current, removed = android_tool.invalidate_stale_croc_build_cache(
            build_root=self.build_root,
            recipe_path=self.recipe_path,
            marker_path=self.marker_path,
        )

        self.assertFalse(removed)
        self.assertEqual(current, fingerprint)
        self.assertTrue(all((path / "stale").is_file() for path in cached_paths))


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

            build_info = json.loads(
                (
                    prepared / "moontransfer" / "build-info.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(build_info["croc_version"], "11.0.1")
            self.assertEqual(build_info["protocol_version"], 2)
            self.assertRegex(
                build_info["version"],
                (
                    r"^0\.1\.0-(?:(?:alpha|beta|rc)\.\d+|"
                    r"dev(?:\.[0-9a-f]{12})?)$"
                ),
            )

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

    def test_cancel_action_is_explicit_immutable_and_session_bound(self) -> None:
        runtime_source = (
            ROOT
            / "android"
            / "app"
            / "moontransfer_android"
            / "android_runtime.py"
        ).read_text(encoding="utf-8")
        action_source = (
            ROOT
            / "android"
            / "java"
            / "io"
            / "github"
            / "gaumeloth"
            / "moontransfer"
            / "TransferNotificationAction.java"
        ).read_text(encoding="utf-8")

        self.assertIn("_add_cancel_transfer_action", runtime_source)
        self.assertIn("helper.addCancelAction", runtime_source)
        self.assertNotIn("builder.addAction", runtime_source)
        self.assertIn('context.getPackageName() + ".ServiceTransfer"', action_source)
        self.assertIn("PendingIntent.FLAG_IMMUTABLE", action_source)
        self.assertIn("PendingIntent.FLAG_CANCEL_CURRENT", action_source)
        self.assertIn("intent.putExtra(EXTRA_SESSION_ID, sessionId)", action_source)
        self.assertIn('"Interrompi"', action_source)


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

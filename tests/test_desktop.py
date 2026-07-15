from __future__ import annotations

import unittest
from pathlib import Path

from moontransfer.desktop import external_process_environment, folder_open_command


class DesktopTests(unittest.TestCase):
    def test_linux_folder_open_command_prefers_xdg_open(self) -> None:
        path = "/usr/bin/xdg-open"

        self.assertEqual(
            folder_open_command(
                Path("/tmp"),
                platform_name="linux",
                which=lambda command: path if command == "xdg-open" else None,
            ),
            [path, "/tmp"],
        )

    def test_linux_folder_open_command_falls_back_to_gio(self) -> None:
        self.assertEqual(
            folder_open_command(
                Path("/tmp"),
                platform_name="linux",
                which=lambda command: "/usr/bin/gio" if command == "gio" else None,
            ),
            ["/usr/bin/gio", "open", "/tmp"],
        )

    def test_unknown_folder_open_command_returns_none(self) -> None:
        self.assertIsNone(
            folder_open_command(
                Path("/tmp"),
                platform_name="unknown",
                which=lambda command: None,
            )
        )

    def test_external_process_environment_restores_original_library_path(self) -> None:
        self.assertEqual(
            external_process_environment(
                {
                    "LD_LIBRARY_PATH": "/tmp/app/_internal",
                    "LD_LIBRARY_PATH_ORIG": "/usr/lib",
                },
                frozen=True,
            ),
            {"LD_LIBRARY_PATH": "/usr/lib"},
        )

    def test_external_process_environment_removes_empty_original_library_path(self) -> None:
        self.assertEqual(
            external_process_environment(
                {
                    "LD_LIBRARY_PATH": "/tmp/app/_internal",
                    "LD_LIBRARY_PATH_ORIG": "",
                },
                frozen=True,
            ),
            {},
        )

    def test_external_process_environment_removes_frozen_qt_paths(self) -> None:
        self.assertEqual(
            external_process_environment(
                {
                    "LD_LIBRARY_PATH": "/tmp/app/_internal",
                    "QT_PLUGIN_PATH": "/tmp/app/qt/plugins",
                    "QML2_IMPORT_PATH": "/tmp/app/qml",
                    "QT_QPA_PLATFORM_PLUGIN_PATH": "/tmp/app/platforms",
                    "PATH": "/usr/bin",
                },
                frozen=True,
            ),
            {"PATH": "/usr/bin"},
        )

    def test_external_process_environment_keeps_normal_library_path(self) -> None:
        self.assertEqual(
            external_process_environment(
                {"LD_LIBRARY_PATH": "/custom/lib"},
                frozen=False,
            ),
            {"LD_LIBRARY_PATH": "/custom/lib"},
        )


if __name__ == "__main__":
    unittest.main()

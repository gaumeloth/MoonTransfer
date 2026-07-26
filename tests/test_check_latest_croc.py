from __future__ import annotations

import unittest
from pathlib import Path

from tools import check_latest_croc


class LatestCrocCheckTests(unittest.TestCase):
    def test_has_update(self) -> None:
        check = check_latest_croc.LatestCrocCheck(
            pinned_version="10.4.13",
            latest_version="10.4.14",
        )

        self.assertTrue(check.has_update)

    def test_has_no_update_for_same_version(self) -> None:
        check = check_latest_croc.LatestCrocCheck(
            pinned_version="10.4.13",
            latest_version="10.4.13",
        )

        self.assertFalse(check.has_update)

    def test_checksum_asset_name(self) -> None:
        self.assertEqual(
            check_latest_croc.checksum_asset_name("v10.4.13"),
            "croc_v10.4.13_checksums.txt",
        )

    def test_checksum_download_url(self) -> None:
        self.assertEqual(
            check_latest_croc.checksum_download_url("10.4.13"),
            "https://github.com/schollz/croc/releases/download/"
            "v10.4.13/croc_v10.4.13_checksums.txt",
        )

    def test_expected_release_hash_requires_asset_from_checksum_file(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "does not list"):
            check_latest_croc.expected_release_hash("missing.zip", {})

    def test_expected_release_hash_normalizes_sha256(self) -> None:
        self.assertEqual(
            check_latest_croc.expected_release_hash(
                "asset.zip",
                {
                    "asset.zip": (
                        "sha256:"
                        "ABCDEFabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234"
                    )
                },
            ),
            "abcdefabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234",
        )

    def test_smoke_command_args_use_moontransfer_flags(self) -> None:
        commands = check_latest_croc.smoke_command_args(Path("/tmp/croc"))

        flattened = [" ".join(command) for command in commands]
        self.assertIn("/tmp/croc --version", flattened)
        self.assertIn(
            "/tmp/croc --classic=false --ignore-stdin --disable-clipboard "
            "send --no-local --help",
            flattened,
        )
        self.assertIn(
            "/tmp/croc --classic=false --ignore-stdin --yes --overwrite --help",
            flattened,
        )

    def test_compatibility_environment_drops_maintainer_secrets(self) -> None:
        environment = check_latest_croc.compatibility_process_environment(
            Path("/tmp/croc-config"),
            base_env={
                "GITHUB_TOKEN": "github-secret",
                "SSH_AUTH_SOCK": "/tmp/agent.sock",
                "AWS_SECRET_ACCESS_KEY": "cloud-secret",
                "LD_PRELOAD": "/tmp/injected.so",
                "HTTPS_PROXY": "http://proxy.example",
                "LANG": "it_IT.UTF-8",
            },
        )

        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertNotIn("SSH_AUTH_SOCK", environment)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)
        self.assertNotIn("LD_PRELOAD", environment)
        self.assertEqual(environment["HTTPS_PROXY"], "http://proxy.example")
        self.assertEqual(environment["LANG"], "it_IT.UTF-8")
        self.assertEqual(environment["HOME"], "/tmp/croc-config/home")


if __name__ == "__main__":
    unittest.main()

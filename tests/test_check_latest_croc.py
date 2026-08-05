from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

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
        binary = Path("/tmp/croc")
        commands = check_latest_croc.smoke_command_args(binary)

        flattened = [" ".join(command) for command in commands]
        program = str(binary)
        self.assertIn(f"{program} --version", flattened)
        self.assertIn(
            f"{program} --classic=false --ignore-stdin --disable-clipboard "
            "send --no-local --help",
            flattened,
        )
        self.assertIn(
            f"{program} --classic=false --ignore-stdin --yes --overwrite --help",
            flattened,
        )

    def test_compatibility_environment_drops_maintainer_secrets(self) -> None:
        config_dir = Path("/tmp/croc-config")
        environment = check_latest_croc.compatibility_process_environment(
            config_dir,
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
        self.assertEqual(environment["HOME"], str(config_dir / "home"))

    def test_transfer_pairs_include_same_and_mixed_versions(self) -> None:
        latest = check_latest_croc.CrocBinary(
            version="11.0.1",
            path=Path("/tmp/croc-11"),
        )
        compatible = check_latest_croc.CrocBinary(
            version="10.7.0",
            path=Path("/tmp/croc-10"),
        )

        pairs = check_latest_croc.transfer_pairs(latest, compatible)

        self.assertEqual(
            [(sender.version, receiver.version) for sender, receiver in pairs],
            [
                ("11.0.1", "11.0.1"),
                ("10.7.0", "11.0.1"),
                ("11.0.1", "10.7.0"),
            ],
        )

    def test_transfer_pairs_skip_duplicate_compatibility_version(self) -> None:
        latest = check_latest_croc.CrocBinary(
            version="11.0.1",
            path=Path("/tmp/croc-11"),
        )
        same_version = check_latest_croc.CrocBinary(
            version="11.0.1",
            path=Path("/tmp/other-croc-11"),
        )

        self.assertEqual(
            check_latest_croc.transfer_pairs(latest, same_version),
            ((latest, latest),),
        )

    def test_compat_version_requires_transfer(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            check_latest_croc.parse_args(["--compat-version", "10.7.0"])

    @mock.patch("tools.check_latest_croc.run_transfer_test")
    def test_transfer_matrix_skips_prompts_after_handshake_failure(
        self,
        run_transfer_test: mock.Mock,
    ) -> None:
        latest = check_latest_croc.CrocBinary("11.0.1", Path("/tmp/croc-11"))
        compatible = check_latest_croc.CrocBinary("10.7.0", Path("/tmp/croc-10"))

        def fail_mixed_sender(sender, **kwargs):
            receiver = kwargs["receiver_binary"]
            if sender.version == "10.7.0" and receiver.version == "11.0.1":
                raise RuntimeError("incompatible protocol")

        run_transfer_test.side_effect = fail_mixed_sender

        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(
            RuntimeError,
            "failed in 1 case",
        ):
            check_latest_croc.run_transfer_matrix(latest, compatible=compatible)

        calls_by_pair = [
            (
                call.args[0].version,
                call.kwargs["receiver_binary"].version,
                call.kwargs.get("prompt_response"),
            )
            for call in run_transfer_test.call_args_list
        ]
        self.assertEqual(
            calls_by_pair,
            [
                ("11.0.1", "11.0.1", None),
                ("11.0.1", "11.0.1", True),
                ("11.0.1", "11.0.1", False),
                ("10.7.0", "11.0.1", None),
                ("11.0.1", "10.7.0", None),
                ("11.0.1", "10.7.0", True),
                ("11.0.1", "10.7.0", False),
            ],
        )


if __name__ == "__main__":
    unittest.main()

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from moontransfer.app import ReceiveTab
from moontransfer.files import create_session_paths
from moontransfer.payload import scan_source_payload
from moontransfer.protocol import ProtocolError, read_proposal, write_control_file
from moontransfer.transfer import ReceiveSession, SaveFailure, TransferState
from tests.test_app import _FakeCrocRunner, _wait_until


class TransferUsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def test_container_roundtrip_default_and_invalid_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = (root / "a.txt", root / "b.txt")
            for path in paths:
                path.write_text("test")
            payload = scan_source_payload(paths)
            proposal = payload.create_proposal("Foto viaggio")
            metadata = root / "proposal.json"
            write_control_file(metadata, proposal)
            self.assertEqual(read_proposal(metadata).destination_name, "Foto viaggio")
            data = json.loads(metadata.read_text())
            data.pop("container_name")
            metadata.write_text(json.dumps(data))
            self.assertEqual(read_proposal(metadata).destination_name, "MoonTransfer")
            for name in ("../bad", "CON", "", 42, "a/b"):
                data["container_name"] = name
                metadata.write_text(json.dumps(data))
                with self.subTest(name=name), self.assertRaises(ProtocolError):
                    read_proposal(metadata)
            self.assertEqual(scan_source_payload(paths[:1]).create_proposal("ignored").destination_name, "a.txt")

    def make_tab(self):
        settings = Mock()
        settings.value.return_value = ""
        with patch("moontransfer.app.CrocRunner", _FakeCrocRunner), patch("moontransfer.app.QSettings", return_value=settings):
            tab = ReceiveTab("croc")
        self.addCleanup(tab.close)
        return tab

    def test_desktop_normalizes_without_starting_and_rejects_ambiguity(self):
        tab = self.make_tab()
        with patch.object(tab.controller, "start") as start:
            tab.code_edit.setText("Codice MoonTransfer: " + "A" * 32 + "\nMessaggio.")
            self.assertEqual(tab.code_edit.text(), "a" * 32)
            start.assert_not_called()
            tab.code_edit.setText("a" * 32 + " " + "b" * 32)
            self.assertFalse(tab.start_button.isEnabled())

    def test_desktop_save_failure_can_retry_without_network_and_without_overwrite(self):
        tab = self.make_tab()
        controller = tab.controller
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "file.bin"
            source.write_bytes(b"payload")
            proposal = scan_source_payload((source,)).create_proposal()
            paths = create_session_paths()
            (paths.main_receive / source.name).write_bytes(b"payload")
            destination = root / "destination"
            destination.mkdir()
            target = destination / source.name
            target.write_bytes(b"existing")
            controller.session = ReceiveSession("a" * 32, destination, paths=paths,
                                                proposal=proposal, target_path=target)
            controller.machine.state = TransferState.VERIFYING
            try:
                with patch("moontransfer.transfer.publish_received_payload", side_effect=OSError("Disk full")):
                    result = controller._verify_and_store_payload(
                        staging=paths.main_receive, proposal=proposal, target_path=target,
                        target_overwrite=False, cancel_requested=lambda: False,
                    )
                self.assertIsInstance(result, SaveFailure)
                controller._on_received_payload_stored(result)
                self.assertEqual(controller.state, TransferState.AWAITING_SAVE)
                self.assertTrue(tab.dest_button.isEnabled())
                self.assertTrue(paths.main_receive.exists())
                controller.retry_save(destination)
                _wait_until(lambda: controller.state == TransferState.COMPLETED)
                self.assertEqual(target.read_bytes(), b"existing")
                self.assertEqual(len(list(destination.iterdir())), 2)
                self.assertIn("salvato", tab.result_label.text())
                self.assertFalse(paths.root.exists())
                self.assertTrue(all(not runner.starts for runner in tab.runners.values()))
            finally:
                controller.stop()

    def test_integrity_failure_is_not_recoverable_save_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "a"
            source.write_bytes(b"original")
            proposal = scan_source_payload((source,)).create_proposal()
            source.write_bytes(b"modified")
            from moontransfer.transfer import ReceiveTransferController
            with self.assertRaises(ValueError):
                ReceiveTransferController._verify_and_store_payload(
                    staging=root, proposal=proposal, target_path=root / "saved",
                    target_overwrite=False, cancel_requested=lambda: False,
                )

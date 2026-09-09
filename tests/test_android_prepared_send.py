import tempfile
import unittest
from pathlib import Path
from threading import Event

from moontransfer_android.sender import AndroidSendCallbacks, AndroidSendController, AndroidSendState
from moontransfer_android.service_protocol import (
    TransferServiceStateStore, create_send_service_request,
    read_service_request, read_service_snapshot,
)
from tests.test_android_sender import _FakeRunner, _stage_file


class PreparedSendTests(unittest.TestCase):
    def test_new_send_rehashes_prepared_copy_and_generates_fresh_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = _stage_file(root)
            prepared = []
            for _ in range(2):
                runner = _FakeRunner()
                controller = AndroidSendController(
                    metadata_runner=runner, main_runner=runner,
                    sessions_parent=root / "sessions", retain_selection=True,
                    callbacks=AndroidSendCallbacks(on_prepared=lambda proposal, code: prepared.append((proposal, code))),
                )
                controller.start(document)
                self.assertTrue(controller.wait(5))
                self.assertEqual(controller.state, AndroidSendState.COMPLETED)
                self.assertTrue(document.path.exists())
            self.assertNotEqual(prepared[0][1], prepared[1][1])
            self.assertNotEqual(prepared[0][0].main_code, prepared[1][0].main_code)
            self.assertEqual(prepared[0][0].entries, prepared[1][0].entries)

    def test_explicit_cancel_discards_copy_even_when_retention_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = _stage_file(root)
            runner = _FakeRunner(block=True)
            ready = Event()
            controller = AndroidSendController(
                metadata_runner=runner, main_runner=runner,
                sessions_parent=root / "sessions", retain_selection=True,
                callbacks=AndroidSendCallbacks(on_prepared=lambda *_: ready.set()),
            )
            try:
                controller.start(document)
                self.assertTrue(ready.wait(3))
                controller.cancel()
                self.assertTrue(controller.wait(5))
                self.assertEqual(controller.state, AndroidSendState.CANCELLED)
                self.assertFalse(document.staging_dir.exists())
            finally:
                controller.cancel()
                controller.wait(5)

    def test_service_request_preserves_container_and_snapshot_preserves_saved_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = _stage_file(root)
            request = create_send_service_request(root, document, container_name="Viaggio")
            self.assertEqual(read_service_request(root, request.session_id).container_name, "Viaggio")
            store = TransferServiceStateStore(root, request)
            store.update(saved_uri="content://provider/document/1")
            self.assertEqual(read_service_snapshot(root, request.session_id).saved_uri, "content://provider/document/1")

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from moontransfer.protocol import create_proposal
from moontransfer_android.documents import document_action
from moontransfer_android.receiver import AndroidReceiveCallbacks, AndroidReceiveController, AndroidReceiveState
from tests.test_android_receiver import _FakeRunner, _wait


class AndroidSaveRecoveryTests(unittest.TestCase):
    def test_save_failure_retries_verified_copy_without_receiving_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = b"payload"
            proposal = create_proposal(filename="a.bin", size=len(content), sha256=hashlib.sha256(content).hexdigest())
            runner = _FakeRunner(proposal, content=content)
            ready = Event()
            finished = Event()
            saved = []
            statuses = []
            attempts = []

            def save(source, uri, **kwargs):
                attempts.append(uri)
                self.assertEqual(source.read_bytes(), content)
                if len(attempts) == 1:
                    raise OSError("provider unavailable")
                return len(content)

            controller = AndroidReceiveController(
                runner=runner, sessions_parent=root / "sessions", main_receive_delay=0,
                save_file=save,
                callbacks=AndroidReceiveCallbacks(
                    on_proposal=lambda _: controller.accept(),
                    on_save_ready=lambda _: ready.set(), on_saved=saved.append,
                    on_status=statuses.append, on_finished=lambda *_: finished.set(),
                ),
            )
            try:
                controller.start("a" * 32)
                _wait(ready, "save not ready")
                ready.clear()
                controller.save_to_uri("content://failed/document")
                _wait(ready, "retry not offered")
                self.assertEqual(controller.state, AndroidReceiveState.AWAITING_SAVE)
                self.assertTrue(any("provider unavailable" in item for item in statuses))
                controller.save_to_uri("content://good/document")
                _wait(finished, "save did not finish")
                self.assertTrue(controller.wait(1))
                self.assertEqual(controller.state, AndroidReceiveState.COMPLETED)
                self.assertEqual(saved, ["content://good/document"])
                self.assertEqual(len(runner.calls), 2)
                self.assertEqual(list((root / "sessions").iterdir()), [])
            finally:
                controller.cancel()
                controller.wait(1)

    def test_unclaimed_verified_content_expires_and_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal = create_proposal(filename="a", size=7, sha256=hashlib.sha256(b"payload").hexdigest())
            finished = Event()
            save = Mock()
            controller = AndroidReceiveController(
                runner=_FakeRunner(proposal), sessions_parent=root / "sessions",
                main_receive_delay=0, save_file=save,
                callbacks=AndroidReceiveCallbacks(
                    on_proposal=lambda _: controller.accept(),
                    on_finished=lambda *_: finished.set(),
                ),
            )
            with patch("moontransfer_android.receiver.SAVE_RETENTION_SECONDS", 0):
                controller.start("a" * 32)
                _wait(finished, "retention did not expire")
                self.assertTrue(controller.wait(1))
            self.assertEqual(controller.state, AndroidReceiveState.FAILED)
            self.assertEqual(list((root / "sessions").iterdir()), [])
            save.assert_not_called()


class DocumentActionTests(unittest.TestCase):
    def test_save_picker_restores_location_and_replaces_persisted_grant(self):
        from moontransfer_android.storage import AndroidSavePicker
        picker = AndroidSavePicker.__new__(AndroidSavePicker)
        picker._activity = Mock()
        picker._activity_class = SimpleNamespace(RESULT_OK=-1)
        picker._intent_class = Mock()
        picker._intent_class.FLAG_GRANT_READ_URI_PERMISSION = 1
        picker._intent_class.FLAG_GRANT_WRITE_URI_PERMISSION = 2
        picker._on_selected = None
        selected = Mock()
        error = Mock()
        uri = Mock()
        uri.toString.return_value = "content://provider/new"
        result = Mock()
        result.getData.return_value = uri
        result.getFlags.return_value = 3
        Uri = Mock()
        bridge = SimpleNamespace(autoclass=lambda _: Uri, cast=lambda _, value: value)
        with patch.dict(sys.modules, jnius=bridge):
            picker.open("a.txt", initial_uri="content://provider/old", on_selected=selected,
                        on_cancelled=Mock(), on_error=error)
            picker._intent_class.return_value.putExtra.assert_any_call(
                "android.provider.extra.INITIAL_URI", Uri.parse.return_value,
            )
            picker._on_activity_result(picker._request_code, -1, result)
        selected.assert_called_once_with(uri)
        error.assert_not_called()
        resolver = picker._activity.getContentResolver.return_value
        resolver.takePersistableUriPermission.assert_called_once_with(uri, 3)
        resolver.releasePersistableUriPermission.assert_called_once_with(Uri.parse.return_value, 3)

    def test_native_actions_delegate_to_typed_activity_bridge(self):
        for share, directory in ((False, False), (True, False), (False, True)):
            with self.subTest(share=share, directory=directory):
                activity = Mock()
                # Any attempt to construct Intent/CharSequence in Python must fail.
                classes = {"org.kivy.android.PythonActivity": SimpleNamespace(mActivity=activity)}
                cast = Mock(return_value=activity)
                bridge = SimpleNamespace(autoclass=classes.__getitem__, cast=cast)
                with patch.dict(sys.modules, jnius=bridge):
                    document_action("content://provider/document/1", share=share, directory=directory)
                cast.assert_called_once_with("io.github.gaumeloth.moontransfer.MoonTransferActivity", activity)
                activity.openSavedDocument.assert_called_once_with("content://provider/document/1", share, directory)

    def test_private_paths_and_directory_share_are_rejected_before_bridge(self):
        for uri in ("file:///private/file", "/private/file", "content:///missing-provider"):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                document_action(uri)
        with self.assertRaises(ValueError):
            document_action("content://provider/folder", directory=True, share=True)

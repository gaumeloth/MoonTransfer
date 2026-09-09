from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

from tests.test_android_sharing import CODE, OTHER_CODE, intent
from moontransfer_android.service_protocol import TransferServiceOperation
from moontransfer_android.sender import AndroidSendState


@unittest.skipUnless(
    os.environ.get("MOONTRANSFER_KIVY_TOUCH_TESTS") == "1"
    and importlib.util.find_spec("kivy"),
    "Requires opt-in Kivy tests and an OpenGL context",
)
class AndroidSharingUiTests(unittest.TestCase):
    def setUp(self):
        from moontransfer_android.application import MoonTransferAndroidApp
        self.platform = patch("moontransfer_android.application.platform", "android")
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.app = MoonTransferAndroidApp()
        self.app.root = self.app.build()
        self.addCleanup(self.cleanup_app)

    def cleanup_app(self):
        from kivy.animation import Animation
        from kivy.lang import Builder
        from moontransfer_android.application import KV_PATH
        self.app.on_stop()
        if self.app._snackbar_event is not None:
            self.app._snackbar_event.cancel()
        for widget in self.app.root.walk():
            Animation.cancel_all(widget)
        Builder.unload_file(str(KV_PATH))

    def test_shared_code_opens_receive_without_starting_transfer(self):
        self.app._start_receive = Mock()
        self.app._handle_shared_intent(intent(text=CODE))
        self.assertEqual(self.app.receive_code_input.text, CODE)
        self.assertEqual(self.app._view_manager.current, "receive")
        self.assertIsNone(self.app._service_client)
        self.app._start_receive.assert_not_called()

    def test_received_document_actions_require_completed_saved_content(self):
        from moontransfer_android.receiver import AndroidReceiveState
        self.app._receive_proposal = SimpleNamespace(filename="file.txt", size=12, is_single_file=True)
        self.app._saved_uri = "content://provider/document/1"
        self.app._receive_state = AndroidReceiveState.COMPLETED
        self.app._configure_receive_result(AndroidReceiveState.COMPLETED, "Salvato")
        self.assertFalse(self.app.root.ids.receive_open_button.disabled)
        self.assertFalse(self.app.root.ids.receive_share_button.disabled)
        with patch("moontransfer_android.application.document_action") as action:
            self.app.root.ids.receive_share_button.dispatch("on_release")
            action.assert_called_once_with(self.app._saved_uri, share=True, directory=False)
        self.app._receive_proposal.is_single_file = False
        self.app._configure_receive_result(AndroidReceiveState.COMPLETED, "Salvato")
        self.assertTrue(self.app.root.ids.receive_share_button.disabled)
        self.assertFalse(self.app.root.ids.receive_open_button.disabled)
        self.app._configure_receive_result(AndroidReceiveState.FAILED, "Errore")
        self.assertTrue(self.app.root.ids.receive_open_button.disabled)

    def test_destination_preference_is_private_and_rejects_non_content_uri(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(type(self.app), "user_data_dir", new_callable=PropertyMock, return_value=tmp):
            self.assertIsNone(self.app._destination_preference())
            self.app._destination_preference("content://provider/document/1")
            self.assertEqual(self.app._destination_preference(), "content://provider/document/1")
            self.app._destination_preference("file:///private/file")
            self.assertIsNone(self.app._destination_preference())

    def test_document_bridge_error_is_not_reported_as_missing_handler(self):
        from moontransfer_android.receiver import AndroidReceiveState
        self.app._receive_proposal = SimpleNamespace(is_single_file=False)
        self.app._saved_uri = "content://provider/folder/1"
        self.app._receive_state = AndroidReceiveState.COMPLETED
        with patch("moontransfer_android.application.document_action", side_effect=RuntimeError("JNI overload error")):
            self.app._open_received()
        self.assertEqual(self.app._dialog_overlay.title, "Azione non avviata")
        self.assertIn("Errore interno", self.app._dialog_overlay.message)
        self.assertNotIn("Nessuna app compatibile", self.app._dialog_overlay.message)
        self.assertEqual(self.app._saved_uri, "content://provider/folder/1")

    def test_manifest_details_are_paged_and_can_return_to_start(self):
        from moontransfer.protocol import PayloadEntry, create_payload_proposal
        proposal = create_payload_proposal(
            roots=("folder",),
            entries=(PayloadEntry(path="folder", type="directory"),) + tuple(
                PayloadEntry(path=f"folder/{index}.txt", type="file", size=0, sha256="a" * 64)
                for index in range(30)
            ),
        )
        self.app._display_payload_details(proposal)
        self.assertIn("1-20", self.app._dialog_overlay.message)
        self.app._dialog_overlay.invoke_secondary()
        self.assertIn("21-31", self.app._dialog_overlay.message)
        self.app._dialog_overlay.invoke_secondary()
        self.assertIn("1-20", self.app._dialog_overlay.message)

    def test_existing_receive_code_requires_confirmation(self):
        self.app.receive_code_input.text = OTHER_CODE
        self.app._handle_shared_intent(intent(text=CODE))
        self.assertEqual(self.app.receive_code_input.text, OTHER_CODE)
        self.assertIsNotNone(self.app._dialog_overlay)
        self.app._dialog_overlay.invoke_secondary()
        self.assertEqual(self.app.receive_code_input.text, CODE)
        self.assertIsNone(self.app._dialog_overlay)

    def test_ambiguous_share_preserves_existing_code(self):
        self.app.receive_code_input.text = OTHER_CODE
        self.app._handle_shared_intent(intent(text=f"{CODE} {OTHER_CODE}"))
        self.assertEqual(self.app.receive_code_input.text, OTHER_CODE)
        self.assertIn("codici", self.app._dialog_overlay.title)

    def test_active_transfer_is_not_replaced_by_files_or_code(self):
        client = SimpleNamespace(operation=TransferServiceOperation.SEND)
        self.app._service_client = client
        self.app._send_state = AndroidSendState.AWAITING_DECISION
        self.app._stage_selected_uri = Mock()
        for incoming in (intent(text=CODE), intent(streams=("content://files/1",))):
            self.app._handle_shared_intent(incoming)
            self.assertIs(self.app._service_client, client)
            self.assertEqual(self.app._send_state, AndroidSendState.AWAITING_DECISION)
            self.assertEqual(self.app.receive_code_input.text, "")
            self.assertEqual(self.app._dialog_overlay.title, "MoonTransfer occupato")
        self.app._stage_selected_uri.assert_not_called()
        self.app._service_client = None

    def test_external_files_use_staging_without_sending(self):
        self.app._stage_selected_uri = Mock()
        self.app._start_send = Mock()
        self.app._handle_shared_intent(intent(streams=("content://files/1",)))
        self.app._stage_selected_uri.assert_called_once_with(("content://files/1",), is_directory=False, shared=True)
        self.app._start_send.assert_not_called()
        self.assertEqual(self.app._view_manager.current, "send")

    def test_directory_fallback_opens_picker_only_on_explicit_action(self):
        self.app._open_directory_picker = Mock()
        self.app._staging = True
        self.app._shared_directory_unavailable("Accesso mancante")
        self.assertFalse(self.app._staging)
        self.app._open_directory_picker.assert_not_called()
        self.app._dialog_overlay.invoke_secondary()
        self.app._open_directory_picker.assert_called_once()

    def test_share_button_uses_current_code(self):
        with patch("moontransfer_android.application.share_code") as share:
            self.app._code = CODE
            self.app._update_controls()
            self.assertFalse(self.app.share_button.disabled)
            self.app.share_button.dispatch("on_release")
            share.assert_called_once_with(CODE)
            self.app._code = None
            self.app._update_controls()
            self.assertTrue(self.app.share_button.disabled)

    def test_poll_consumes_each_native_intent_once(self):
        self.app._share_activity = Mock()
        self.app._share_activity.consumeSharedIntent.side_effect = [intent(text=CODE), None]
        self.app._poll_shared_intents()
        self.assertEqual(self.app.receive_code_input.text, CODE)
        self.app.receive_code_input.text = OTHER_CODE
        self.app._poll_shared_intents()
        self.assertEqual(self.app.receive_code_input.text, OTHER_CODE)

    def test_paste_button_extracts_code_from_message_without_receiving(self):
        from moontransfer_android.sharing import shared_code_message
        self.app._start_receive = Mock()
        self.app.receive_code_input.text = OTHER_CODE
        with patch("moontransfer_android.application.Clipboard.paste", return_value=shared_code_message(CODE)):
            self.app._paste_receive_code()
        self.assertEqual(self.app.receive_code_input.text, CODE)
        self.assertTrue(self.app._receive_code_is_valid())
        self.assertIsNone(self.app._service_client)
        self.app._start_receive.assert_not_called()

    def test_paste_button_preserves_previous_code_on_invalid_or_ambiguous_text(self):
        for text in ("Nessun codice", f"{CODE}\n{OTHER_CODE}", "x" * 8193):
            with self.subTest(text=text[:80]):
                self.app.receive_code_input.text = CODE
                with patch("moontransfer_android.application.Clipboard.paste", return_value=text):
                    self.app._paste_receive_code()
                self.assertEqual(self.app.receive_code_input.text, CODE)
                self.assertIsNotNone(self.app._dialog_overlay)
                self.app._dialog_overlay.invoke_primary()

    def test_native_paste_extracts_complete_spaced_uppercase_and_repeated_codes(self):
        from kivy.clock import Clock
        from moontransfer_android.sharing import shared_code_message
        field = self.app.receive_code_input
        spaced = " ".join(CODE[i:i + 8] for i in range(0, 32, 8))
        for text in (shared_code_message(CODE), f"Codice: {spaced.upper()}\nFine.", f"{CODE}\n{CODE}"):
            with self.subTest(text=text):
                field.text = ""
                Clock.tick()
                with patch("kivy.uix.textinput.Clipboard.paste", return_value=text):
                    field.paste()
                Clock.tick()
                self.assertEqual(field.text, CODE)
                self.assertTrue(self.app._receive_code_is_valid())
                self.assertIsNone(self.app._service_client)
                field.cursor = (len(CODE), 0)
                field.do_backspace()
                Clock.tick()
                self.assertEqual(field.text, CODE[:-1])
                field.insert_text(CODE[-1])
                Clock.tick()
                self.assertEqual(field.text, CODE)

    def test_field_keeps_partial_invalid_and_ambiguous_input_editable(self):
        from kivy.clock import Clock
        field = self.app.receive_code_input
        for text in (CODE[:12], "Testo senza codice", f"{CODE} {OTHER_CODE}"):
            with self.subTest(text=text):
                field.text = ""
                Clock.tick()
                field.insert_text(text)
                Clock.tick()
                self.assertEqual(field.text, text)
                self.assertFalse(self.app._receive_code_is_valid())
                self.assertTrue(self.app.receive_start_button.disabled)

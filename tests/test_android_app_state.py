from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANDROID_APP = ROOT / "android" / "app"
sys.path.insert(0, str(ANDROID_APP))

from moontransfer_android.app_state import (  # noqa: E402
    ACTIVE_RECEIVE_STATES,
    ACTIVE_SEND_STATES,
    AndroidControlContext,
    derive_android_control_state,
    project_service_snapshot,
)
from moontransfer_android.receiver import AndroidReceiveState  # noqa: E402
from moontransfer_android.sender import AndroidSendState  # noqa: E402
from moontransfer_android.service_protocol import (  # noqa: E402
    TransferServiceError,
    TransferServiceOperation,
    TransferServiceSnapshot,
)


def _snapshot(
    operation: TransferServiceOperation,
    state: str,
    *,
    terminal: bool = False,
    service_done: bool = False,
) -> TransferServiceSnapshot:
    return TransferServiceSnapshot(
        version=1,
        revision=1,
        session_id="a" * 32,
        operation=operation,
        state=state,
        status="status",
        terminal=terminal,
        service_done=service_done,
        heartbeat_ns=1,
    )


def _idle_context() -> AndroidControlContext:
    return AndroidControlContext(
        is_android=True,
        send_state=AndroidSendState.IDLE,
        receive_state=AndroidReceiveState.IDLE,
        service_operation=None,
        service_releasing=False,
        has_selected_document=True,
        transport_available=True,
        staging=False,
        file_picker_pending=False,
        save_picker_available=True,
        save_picker_pending=False,
        probing=False,
        send_code_available=False,
        receive_code_valid=True,
    )


class AndroidServiceSnapshotProjectionTests(unittest.TestCase):
    def test_projects_send_and_receive_states(self) -> None:
        send = project_service_snapshot(
            _snapshot(TransferServiceOperation.SEND, "sending_file")
        )
        receive = project_service_snapshot(
            _snapshot(TransferServiceOperation.RECEIVE, "awaiting_decision")
        )

        self.assertEqual(send.mode, "send")
        self.assertIs(send.state, AndroidSendState.SENDING_FILE)
        self.assertEqual(receive.mode, "receive")
        self.assertIs(receive.state, AndroidReceiveState.AWAITING_DECISION)

    def test_rejects_unknown_and_incoherent_states(self) -> None:
        with self.assertRaisesRegex(TransferServiceError, "non riconosciuto"):
            project_service_snapshot(
                _snapshot(TransferServiceOperation.SEND, "unknown")
            )
        with self.assertRaisesRegex(TransferServiceError, "terminale.*incoerente"):
            project_service_snapshot(
                _snapshot(TransferServiceOperation.RECEIVE, "completed")
            )
        with self.assertRaisesRegex(TransferServiceError, "senza uno stato finale"):
            project_service_snapshot(
                _snapshot(
                    TransferServiceOperation.RECEIVE,
                    "receiving_file",
                    service_done=True,
                )
            )

    def test_rejects_a_snapshot_for_a_different_requested_operation(self) -> None:
        with self.assertRaisesRegex(
            TransferServiceError,
            "non corrisponde all'operazione",
        ):
            project_service_snapshot(
                _snapshot(TransferServiceOperation.RECEIVE, "preparing"),
                expected_operation=TransferServiceOperation.SEND,
            )

    def test_accepts_consistent_terminal_state(self) -> None:
        projection = project_service_snapshot(
            _snapshot(
                TransferServiceOperation.RECEIVE,
                "completed",
                terminal=True,
                service_done=True,
            )
        )

        self.assertIs(projection.state, AndroidReceiveState.COMPLETED)


class AndroidControlStateTests(unittest.TestCase):
    def test_active_state_sets_cover_every_nonterminal_operation_phase(self) -> None:
        self.assertEqual(
            ACTIVE_SEND_STATES,
            frozenset(
                state
                for state in AndroidSendState
                if state
                not in {
                    AndroidSendState.IDLE,
                    AndroidSendState.COMPLETED,
                    AndroidSendState.REJECTED,
                    AndroidSendState.CANCELLED,
                    AndroidSendState.FAILED,
                }
            ),
        )
        self.assertEqual(
            ACTIVE_RECEIVE_STATES,
            frozenset(
                state
                for state in AndroidReceiveState
                if state
                not in {
                    AndroidReceiveState.IDLE,
                    AndroidReceiveState.COMPLETED,
                    AndroidReceiveState.REJECTED,
                    AndroidReceiveState.CANCELLED,
                    AndroidReceiveState.FAILED,
                }
            ),
        )

    def test_idle_ready_state_enables_new_operations(self) -> None:
        controls = derive_android_control_state(_idle_context())

        self.assertTrue(controls.select_file)
        self.assertTrue(controls.start_send)
        self.assertTrue(controls.edit_receive_code)
        self.assertTrue(controls.start_receive)
        self.assertTrue(controls.probe_transport)
        self.assertFalse(controls.cancel_send)
        self.assertFalse(controls.cancel_receive)

    def test_connected_service_blocks_new_work_even_before_first_snapshot(self) -> None:
        controls = derive_android_control_state(
            replace(
                _idle_context(),
                service_operation=TransferServiceOperation.SEND,
            )
        )

        self.assertFalse(controls.select_file)
        self.assertFalse(controls.start_send)
        self.assertFalse(controls.edit_receive_code)
        self.assertFalse(controls.start_receive)
        self.assertFalse(controls.probe_transport)

    def test_send_service_exposes_only_matching_active_actions(self) -> None:
        controls = derive_android_control_state(
            replace(
                _idle_context(),
                send_state=AndroidSendState.AWAITING_DECISION,
                service_operation=TransferServiceOperation.SEND,
                send_code_available=True,
            )
        )

        self.assertTrue(controls.cancel_send)
        self.assertTrue(controls.copy_code)
        self.assertFalse(controls.cancel_receive)
        self.assertFalse(controls.accept_receive)

    def test_receive_decision_and_save_require_the_receive_service(self) -> None:
        decision = derive_android_control_state(
            replace(
                _idle_context(),
                receive_state=AndroidReceiveState.AWAITING_DECISION,
                service_operation=TransferServiceOperation.RECEIVE,
            )
        )
        saving = derive_android_control_state(
            replace(
                _idle_context(),
                receive_state=AndroidReceiveState.AWAITING_SAVE,
                service_operation=TransferServiceOperation.RECEIVE,
            )
        )

        self.assertTrue(decision.accept_receive)
        self.assertTrue(decision.reject_receive)
        self.assertTrue(decision.cancel_receive)
        self.assertTrue(saving.save_receive)
        self.assertTrue(saving.cancel_receive)

    def test_picker_and_release_windows_do_not_start_a_second_service(self) -> None:
        picker = derive_android_control_state(
            replace(_idle_context(), file_picker_pending=True)
        )
        releasing = derive_android_control_state(
            replace(_idle_context(), service_releasing=True)
        )

        self.assertFalse(picker.select_file)
        self.assertFalse(picker.start_send)
        self.assertFalse(picker.start_receive)
        self.assertTrue(releasing.select_file)
        self.assertTrue(releasing.edit_receive_code)
        self.assertFalse(releasing.start_send)
        self.assertFalse(releasing.start_receive)


if __name__ == "__main__":
    unittest.main()

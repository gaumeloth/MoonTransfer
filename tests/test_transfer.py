from __future__ import annotations

import unittest

from moontransfer.transfer import (
    InvalidStateTransition,
    RECEIVE_TRANSITIONS,
    SEND_TRANSITIONS,
    ReceiveDecision,
    TransferState,
    TransferStateMachine,
)


class TransferStateMachineTests(unittest.TestCase):
    def test_send_state_machine_tracks_active_and_terminal_states(self) -> None:
        machine = TransferStateMachine(SEND_TRANSITIONS)

        self.assertEqual(machine.state, TransferState.IDLE)
        self.assertFalse(machine.active)

        machine.transition(TransferState.PREPARING)
        machine.transition(TransferState.TRANSFERRING_METADATA)
        machine.transition(TransferState.AWAITING_DECISION)
        machine.transition(TransferState.TRANSFERRING_FILE)
        machine.transition(TransferState.COMPLETED)

        self.assertEqual(machine.state, TransferState.COMPLETED)
        self.assertFalse(machine.active)

    def test_receive_state_machine_models_rejection_response(self) -> None:
        machine = TransferStateMachine(RECEIVE_TRANSITIONS)

        machine.transition(TransferState.PREPARING)
        machine.transition(TransferState.TRANSFERRING_METADATA)
        machine.transition(TransferState.AWAITING_DECISION)
        machine.transition(TransferState.RESPONDING_TO_DECISION)
        machine.transition(TransferState.REJECTED)

        self.assertEqual(machine.state, TransferState.REJECTED)
        self.assertFalse(machine.active)

    def test_receive_state_machine_models_destination_check(self) -> None:
        machine = TransferStateMachine(RECEIVE_TRANSITIONS)

        machine.transition(TransferState.PREPARING)
        machine.transition(TransferState.TRANSFERRING_METADATA)
        machine.transition(TransferState.AWAITING_DECISION)
        machine.transition(TransferState.CHECKING_DESTINATION)
        machine.transition(TransferState.TRANSFERRING_FILE)
        machine.transition(TransferState.VERIFYING)
        machine.transition(TransferState.COMPLETED)

        self.assertEqual(machine.state, TransferState.COMPLETED)
        self.assertFalse(machine.active)

    def test_invalid_transition_is_rejected_without_changing_state(self) -> None:
        machine = TransferStateMachine(SEND_TRANSITIONS)

        with self.assertRaises(InvalidStateTransition):
            machine.transition(TransferState.COMPLETED)

        self.assertEqual(machine.state, TransferState.IDLE)

    def test_terminal_state_can_start_a_new_session(self) -> None:
        machine = TransferStateMachine(SEND_TRANSITIONS)
        machine.transition(TransferState.PREPARING)
        machine.transition(TransferState.FAILED)

        machine.transition(TransferState.PREPARING)

        self.assertEqual(machine.state, TransferState.PREPARING)
        self.assertTrue(machine.active)


class ReceiveDecisionTests(unittest.TestCase):
    def test_rejection_has_no_destination(self) -> None:
        decision = ReceiveDecision.reject()

        self.assertFalse(decision.accepted)
        self.assertIsNone(decision.target)
        self.assertFalse(decision.overwrite)


if __name__ == "__main__":
    unittest.main()

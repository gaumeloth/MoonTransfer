from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "android" / "app"))

from moontransfer_android.receiver import AndroidReceiveState
from moontransfer_android.sender import AndroidSendState
from moontransfer_android.ui_state import (
    ReceiveViewStage,
    ResultTone,
    SendViewStage,
    receive_result_tone,
    receive_view_stage,
    send_result_tone,
    send_view_stage,
)


class AndroidUiStateTests(unittest.TestCase):
    def test_every_send_state_maps_to_a_view(self) -> None:
        expected = {
            AndroidSendState.IDLE: SendViewStage.SELECTION,
            AndroidSendState.PREPARING: SendViewStage.WAITING,
            AndroidSendState.SENDING_METADATA: SendViewStage.WAITING,
            AndroidSendState.AWAITING_DECISION: SendViewStage.WAITING,
            AndroidSendState.SENDING_FILE: SendViewStage.TRANSFER,
            AndroidSendState.COMPLETED: SendViewStage.RESULT,
            AndroidSendState.REJECTED: SendViewStage.RESULT,
            AndroidSendState.CANCELLED: SendViewStage.RESULT,
            AndroidSendState.FAILED: SendViewStage.RESULT,
        }

        self.assertEqual(
            {state: send_view_stage(state) for state in AndroidSendState},
            expected,
        )

    def test_every_receive_state_maps_to_a_view(self) -> None:
        expected = {
            AndroidReceiveState.IDLE: ReceiveViewStage.CODE,
            AndroidReceiveState.PREPARING: ReceiveViewStage.LOADING,
            AndroidReceiveState.RECEIVING_METADATA: ReceiveViewStage.LOADING,
            AndroidReceiveState.AWAITING_DECISION: ReceiveViewStage.PROPOSAL,
            AndroidReceiveState.RESPONDING_TO_DECISION: (
                ReceiveViewStage.PROPOSAL
            ),
            AndroidReceiveState.RECEIVING_FILE: ReceiveViewStage.TRANSFER,
            AndroidReceiveState.VERIFYING: ReceiveViewStage.TRANSFER,
            AndroidReceiveState.AWAITING_SAVE: ReceiveViewStage.SAVE,
            AndroidReceiveState.SAVING: ReceiveViewStage.SAVE,
            AndroidReceiveState.COMPLETED: ReceiveViewStage.RESULT,
            AndroidReceiveState.REJECTED: ReceiveViewStage.RESULT,
            AndroidReceiveState.CANCELLED: ReceiveViewStage.RESULT,
            AndroidReceiveState.FAILED: ReceiveViewStage.RESULT,
        }

        self.assertEqual(
            {
                state: receive_view_stage(state)
                for state in AndroidReceiveState
            },
            expected,
        )

    def test_terminal_result_tones_distinguish_failure(self) -> None:
        self.assertIs(
            send_result_tone(AndroidSendState.COMPLETED),
            ResultTone.SUCCESS,
        )
        self.assertIs(
            send_result_tone(AndroidSendState.FAILED),
            ResultTone.ERROR,
        )
        self.assertIs(
            send_result_tone(AndroidSendState.CANCELLED),
            ResultTone.NEUTRAL,
        )
        self.assertIs(
            receive_result_tone(AndroidReceiveState.COMPLETED),
            ResultTone.SUCCESS,
        )
        self.assertIs(
            receive_result_tone(AndroidReceiveState.FAILED),
            ResultTone.ERROR,
        )
        self.assertIs(
            receive_result_tone(AndroidReceiveState.REJECTED),
            ResultTone.NEUTRAL,
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from enum import Enum

from moontransfer_android.receiver import AndroidReceiveState
from moontransfer_android.sender import AndroidSendState


class SendViewStage(str, Enum):
    SELECTION = "send_selection"
    WAITING = "send_waiting"
    TRANSFER = "send_transfer"
    RESULT = "send_result"


class ReceiveViewStage(str, Enum):
    CODE = "receive_code"
    LOADING = "receive_loading"
    PROPOSAL = "receive_proposal"
    TRANSFER = "receive_transfer"
    SAVE = "receive_save"
    RESULT = "receive_result"


class ResultTone(str, Enum):
    SUCCESS = "success"
    NEUTRAL = "neutral"
    ERROR = "error"


def send_view_stage(state: AndroidSendState) -> SendViewStage:
    if state is AndroidSendState.IDLE:
        return SendViewStage.SELECTION
    if state in {
        AndroidSendState.PREPARING,
        AndroidSendState.SENDING_METADATA,
        AndroidSendState.AWAITING_DECISION,
    }:
        return SendViewStage.WAITING
    if state is AndroidSendState.SENDING_FILE:
        return SendViewStage.TRANSFER
    return SendViewStage.RESULT


def receive_view_stage(state: AndroidReceiveState) -> ReceiveViewStage:
    if state is AndroidReceiveState.IDLE:
        return ReceiveViewStage.CODE
    if state in {
        AndroidReceiveState.PREPARING,
        AndroidReceiveState.RECEIVING_METADATA,
    }:
        return ReceiveViewStage.LOADING
    if state in {
        AndroidReceiveState.AWAITING_DECISION,
        AndroidReceiveState.RESPONDING_TO_DECISION,
    }:
        return ReceiveViewStage.PROPOSAL
    if state in {
        AndroidReceiveState.RECEIVING_FILE,
        AndroidReceiveState.VERIFYING,
    }:
        return ReceiveViewStage.TRANSFER
    if state in {
        AndroidReceiveState.AWAITING_SAVE,
        AndroidReceiveState.SAVING,
    }:
        return ReceiveViewStage.SAVE
    return ReceiveViewStage.RESULT


def send_result_tone(state: AndroidSendState) -> ResultTone:
    if state is AndroidSendState.COMPLETED:
        return ResultTone.SUCCESS
    if state is AndroidSendState.FAILED:
        return ResultTone.ERROR
    return ResultTone.NEUTRAL


def receive_result_tone(state: AndroidReceiveState) -> ResultTone:
    if state is AndroidReceiveState.COMPLETED:
        return ResultTone.SUCCESS
    if state is AndroidReceiveState.FAILED:
        return ResultTone.ERROR
    return ResultTone.NEUTRAL

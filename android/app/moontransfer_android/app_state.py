from __future__ import annotations

from dataclasses import dataclass

from moontransfer_android.receiver import AndroidReceiveState
from moontransfer_android.sender import AndroidSendState
from moontransfer_android.service_protocol import (
    TransferServiceError,
    TransferServiceOperation,
    TransferServiceSnapshot,
)


ACTIVE_SEND_STATES = frozenset(
    {
        AndroidSendState.PREPARING,
        AndroidSendState.SENDING_METADATA,
        AndroidSendState.AWAITING_DECISION,
        AndroidSendState.SENDING_FILE,
    }
)
ACTIVE_RECEIVE_STATES = frozenset(
    {
        AndroidReceiveState.PREPARING,
        AndroidReceiveState.RECEIVING_METADATA,
        AndroidReceiveState.AWAITING_DECISION,
        AndroidReceiveState.RESPONDING_TO_DECISION,
        AndroidReceiveState.RECEIVING_FILE,
        AndroidReceiveState.VERIFYING,
        AndroidReceiveState.AWAITING_SAVE,
        AndroidReceiveState.SAVING,
    }
)
TERMINAL_SEND_STATES = frozenset(
    {
        AndroidSendState.COMPLETED,
        AndroidSendState.REJECTED,
        AndroidSendState.CANCELLED,
        AndroidSendState.FAILED,
    }
)
TERMINAL_RECEIVE_STATES = frozenset(
    {
        AndroidReceiveState.COMPLETED,
        AndroidReceiveState.REJECTED,
        AndroidReceiveState.CANCELLED,
        AndroidReceiveState.FAILED,
    }
)


@dataclass(frozen=True)
class ServiceSnapshotProjection:
    operation: TransferServiceOperation
    state: AndroidSendState | AndroidReceiveState

    @property
    def mode(self) -> str:
        return self.operation.value


def project_service_snapshot(
    snapshot: TransferServiceSnapshot,
    *,
    expected_operation: TransferServiceOperation | None = None,
) -> ServiceSnapshotProjection:
    if (
        expected_operation is not None
        and snapshot.operation is not expected_operation
    ):
        raise TransferServiceError(
            "Lo stato del servizio non corrisponde all'operazione richiesta."
        )
    if snapshot.operation is TransferServiceOperation.SEND:
        try:
            state: AndroidSendState | AndroidReceiveState = AndroidSendState(
                snapshot.state
            )
        except ValueError as error:
            raise TransferServiceError(
                f"Stato di invio non riconosciuto: {snapshot.state}"
            ) from error
        expected_terminal = state in TERMINAL_SEND_STATES
    else:
        try:
            state = AndroidReceiveState(snapshot.state)
        except ValueError as error:
            raise TransferServiceError(
                f"Stato di ricezione non riconosciuto: {snapshot.state}"
            ) from error
        expected_terminal = state in TERMINAL_RECEIVE_STATES

    if snapshot.terminal != expected_terminal:
        raise TransferServiceError(
            "Stato terminale del servizio incoerente con la fase corrente."
        )
    if snapshot.service_done and not snapshot.terminal:
        raise TransferServiceError(
            "Il servizio risulta terminato senza uno stato finale."
        )
    return ServiceSnapshotProjection(snapshot.operation, state)


@dataclass(frozen=True)
class AndroidControlContext:
    is_android: bool
    send_state: AndroidSendState
    receive_state: AndroidReceiveState
    service_operation: TransferServiceOperation | None
    service_releasing: bool
    has_selected_document: bool
    transport_available: bool
    staging: bool
    file_picker_pending: bool
    save_picker_available: bool
    save_picker_pending: bool
    probing: bool
    send_code_available: bool
    receive_code_valid: bool


@dataclass(frozen=True)
class AndroidControlState:
    select_file: bool
    start_send: bool
    cancel_send: bool
    copy_code: bool
    edit_receive_code: bool
    start_receive: bool
    accept_receive: bool
    reject_receive: bool
    save_receive: bool
    cancel_receive: bool
    probe_transport: bool


def derive_android_control_state(
    context: AndroidControlContext,
) -> AndroidControlState:
    send_active = context.send_state in ACTIVE_SEND_STATES
    receive_active = context.receive_state in ACTIVE_RECEIVE_STATES
    transfer_active = send_active or receive_active
    service_connected = context.service_operation is not None
    transfer_owned = transfer_active or service_connected
    picker_pending = context.file_picker_pending or context.save_picker_pending
    start_blocked = transfer_owned or context.service_releasing

    receive_service = (
        context.service_operation is TransferServiceOperation.RECEIVE
    )
    send_service = context.service_operation is TransferServiceOperation.SEND
    awaiting_decision = (
        context.receive_state is AndroidReceiveState.AWAITING_DECISION
    )
    awaiting_save = context.receive_state is AndroidReceiveState.AWAITING_SAVE

    return AndroidControlState(
        select_file=(
            context.is_android
            and not context.staging
            and not transfer_owned
            and not picker_pending
        ),
        start_send=(
            context.has_selected_document
            and context.transport_available
            and not context.staging
            and not start_blocked
            and not picker_pending
        ),
        cancel_send=send_active and send_service,
        copy_code=context.send_code_available,
        edit_receive_code=not transfer_owned,
        start_receive=(
            context.is_android
            and context.transport_available
            and context.receive_code_valid
            and not context.staging
            and not start_blocked
            and not picker_pending
        ),
        accept_receive=awaiting_decision and receive_service,
        reject_receive=awaiting_decision and receive_service,
        save_receive=(
            awaiting_save
            and receive_service
            and context.save_picker_available
            and not context.save_picker_pending
        ),
        cancel_receive=receive_active and receive_service,
        probe_transport=(
            context.is_android
            and not context.probing
            and not transfer_owned
            and not context.staging
        ),
    )

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from moontransfer_android.android_runtime import (
    start_transfer_service,
    stop_transfer_service,
)
from moontransfer_android.service_protocol import (
    TransferServiceCommandName,
    TransferServiceError,
    TransferServiceOperation,
    TransferServiceRequest,
    TransferServiceSnapshot,
    cleanup_service_session,
    create_receive_service_request,
    create_send_service_request,
    discover_service_requests,
    read_service_snapshot,
    submit_service_command,
)
from moontransfer_android.storage import StagedDocument, StagedSelection


SERVICE_HEARTBEAT_TIMEOUT_SECONDS = 15.0
SERVICE_SNAPSHOT_UNAVAILABLE_TIMEOUT_SECONDS = 15.0


class TransferServiceHeartbeatMonitor:
    def __init__(
        self,
        *,
        timeout_seconds: float = SERVICE_HEARTBEAT_TIMEOUT_SECONDS,
        snapshot_unavailable_timeout_seconds: float = (
            SERVICE_SNAPSHOT_UNAVAILABLE_TIMEOUT_SECONDS
        ),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Il timeout dell'heartbeat deve essere positivo.")
        if snapshot_unavailable_timeout_seconds <= 0:
            raise ValueError(
                "Il timeout di lettura dello stato deve essere positivo."
            )
        self.timeout_seconds = timeout_seconds
        self.snapshot_unavailable_timeout_seconds = (
            snapshot_unavailable_timeout_seconds
        )
        self.clock = clock
        self._heartbeat_ns: int | None = None
        self._observed_at: float | None = None
        self._snapshot_unavailable_at: float | None = None

    def reset(self) -> None:
        self._heartbeat_ns = None
        self._observed_at = None
        self._snapshot_unavailable_at = None

    def snapshot_unavailable_timed_out(self) -> bool:
        now = self.clock()
        if self._snapshot_unavailable_at is None:
            self._snapshot_unavailable_at = now
            return False
        return (
            now - self._snapshot_unavailable_at
            >= self.snapshot_unavailable_timeout_seconds
        )

    def timed_out(self, snapshot: TransferServiceSnapshot) -> bool:
        self._snapshot_unavailable_at = None
        if snapshot.service_done:
            self.reset()
            return False

        now = self.clock()
        if snapshot.heartbeat_ns != self._heartbeat_ns:
            self._heartbeat_ns = snapshot.heartbeat_ns
            self._observed_at = now
            return False

        if self._observed_at is None:
            self._observed_at = now
            return False
        return now - self._observed_at >= self.timeout_seconds


class TransferServiceClient:
    def __init__(
        self,
        cache_root: Path,
        request: TransferServiceRequest,
        *,
        service_starter: Callable[[str, str], None] = start_transfer_service,
        service_stopper: Callable[[], None] = stop_transfer_service,
    ) -> None:
        self.cache_root = cache_root
        self.request = request
        self.service_starter = service_starter
        self.service_stopper = service_stopper

    @classmethod
    def for_send(
        cls,
        cache_root: Path,
        selection: StagedSelection | StagedDocument,
        *,
        service_starter: Callable[[str, str], None] = start_transfer_service,
        service_stopper: Callable[[], None] = stop_transfer_service,
    ) -> TransferServiceClient:
        return cls(
            cache_root,
            create_send_service_request(cache_root, selection),
            service_starter=service_starter,
            service_stopper=service_stopper,
        )

    @classmethod
    def for_receive(
        cls,
        cache_root: Path,
        metadata_code: str,
        *,
        service_starter: Callable[[str, str], None] = start_transfer_service,
        service_stopper: Callable[[], None] = stop_transfer_service,
    ) -> TransferServiceClient:
        return cls(
            cache_root,
            create_receive_service_request(cache_root, metadata_code),
            service_starter=service_starter,
            service_stopper=service_stopper,
        )

    @property
    def session_id(self) -> str:
        return self.request.session_id

    @property
    def operation(self) -> TransferServiceOperation:
        return self.request.operation

    def start(self) -> None:
        description = (
            "Invio in corso"
            if self.operation is TransferServiceOperation.SEND
            else "Ricezione in corso"
        )
        try:
            self.service_starter(self.session_id, description)
        except BaseException:
            cleanup_service_session(self.cache_root, self.session_id)
            raise

    def snapshot(self) -> TransferServiceSnapshot:
        return read_service_snapshot(self.cache_root, self.session_id)

    def accept(self) -> None:
        self._command(TransferServiceCommandName.ACCEPT)

    def reject(self) -> None:
        self._command(TransferServiceCommandName.REJECT)

    def cancel(self) -> None:
        self._command(TransferServiceCommandName.CANCEL)

    def save_to_uri(self, destination_uri: str) -> None:
        self._command(
            TransferServiceCommandName.SAVE,
            destination_uri=destination_uri,
        )

    def cleanup(self) -> None:
        cleanup_service_session(self.cache_root, self.session_id)

    def stop(self) -> None:
        self.service_stopper()

    def _command(
        self,
        command: TransferServiceCommandName,
        *,
        destination_uri: str | None = None,
    ) -> None:
        submit_service_command(
            self.cache_root,
            self.session_id,
            command,
            destination_uri=destination_uri,
        )


def recover_latest_service_client(
    cache_root: Path,
) -> tuple[TransferServiceClient | None, TransferServiceSnapshot | None]:
    requests = discover_service_requests(cache_root)
    if not requests:
        return None, None

    latest_request = requests[0]
    try:
        latest_snapshot = read_service_snapshot(
            cache_root,
            latest_request.session_id,
        )
    except TransferServiceError:
        latest_snapshot = None

    for stale_request in requests[1:]:
        try:
            stale_snapshot = read_service_snapshot(
                cache_root,
                stale_request.session_id,
            )
        except TransferServiceError:
            continue
        if stale_snapshot.service_done:
            cleanup_service_session(cache_root, stale_request.session_id)
    return TransferServiceClient(cache_root, latest_request), latest_snapshot


def request_notification_permission() -> None:
    try:
        from android.permissions import Permission, request_permissions
        from jnius import autoclass
    except ImportError:
        return
    if int(autoclass("android.os.Build$VERSION").SDK_INT) >= 33:
        permission = getattr(
            Permission,
            "POST_NOTIFICATIONS",
            "android.permission.POST_NOTIFICATIONS",
        )
        request_permissions([permission])

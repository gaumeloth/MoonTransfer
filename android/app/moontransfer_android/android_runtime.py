from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ANDROID_PACKAGE_NAME = "io.github.gaumeloth.moontransfer"
TRANSFER_SERVICE_CLASS = f"{ANDROID_PACKAGE_NAME}.ServiceTransfer"
TRANSFER_SERVICE_ID = 1
TRANSFER_RESULT_NOTIFICATION_ID = 2
TRANSFER_NOTIFICATION_CHANNEL = "org.kivy.p4a1"
TRANSFER_CANCEL_ACTION = (
    "io.github.gaumeloth.moontransfer.action.CANCEL_TRANSFER"
)
TRANSFER_SESSION_EXTRA = "io.github.gaumeloth.moontransfer.extra.SESSION_ID"
TRANSFER_SESSION_RE = re.compile(r"^[0-9a-f]{32}$")


class AndroidRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TransferNotification:
    title: str
    text: str
    progress: int | None = None
    indeterminate: bool = False
    public_text: str = "Trasferimento MoonTransfer in corso"
    cancel_session_id: str | None = None

    def __post_init__(self) -> None:
        if self.progress is not None and not 0 <= self.progress <= 100:
            raise ValueError("Avanzamento della notifica non valido.")
        if self.progress is not None and self.indeterminate:
            raise ValueError(
                "Una notifica non può avere avanzamento determinato e "
                "indeterminato insieme."
            )
        if (
            self.cancel_session_id is not None
            and not TRANSFER_SESSION_RE.fullmatch(self.cancel_session_id)
        ):
            raise ValueError("Sessione di annullamento non valida.")


def android_context() -> Any:
    try:
        from jnius import autoclass
    except ImportError as error:
        raise AndroidRuntimeError("Runtime Android non disponibile.") from error

    if os.environ.get("PYTHON_SERVICE_ARGUMENT"):
        context = autoclass("org.kivy.android.PythonService").mService
    else:
        context = autoclass("org.kivy.android.PythonActivity").mActivity
    if context is None:
        raise AndroidRuntimeError("Contesto Android non disponibile.")
    return context


def android_files_dir() -> Path:
    return Path(str(android_context().getFilesDir().getAbsolutePath()))


def ensure_transfer_notification_channel() -> None:
    try:
        from jnius import autoclass
    except ImportError as error:
        raise AndroidRuntimeError("Runtime Android non disponibile.") from error

    build_version = autoclass("android.os.Build$VERSION")
    if int(build_version.SDK_INT) < 26:
        return
    context = android_context()
    channel_class = autoclass("android.app.NotificationChannel")
    manager_class = autoclass("android.app.NotificationManager")
    channel = channel_class(
        TRANSFER_NOTIFICATION_CHANNEL,
        "Trasferimenti MoonTransfer",
        manager_class.IMPORTANCE_LOW,
    )
    channel.setDescription("Stato dei trasferimenti di file in corso")
    notification_class = autoclass("android.app.Notification")
    context_class = autoclass("android.content.Context")
    channel.setLockscreenVisibility(notification_class.VISIBILITY_PRIVATE)
    manager = context.getSystemService(context_class.NOTIFICATION_SERVICE)
    manager.createNotificationChannel(channel)


def start_transfer_service(session_id: str, description: str) -> None:
    try:
        from jnius import autoclass
    except ImportError as error:
        raise AndroidRuntimeError("Runtime Android non disponibile.") from error

    ensure_transfer_notification_channel()
    context = android_context()
    _notification_manager(context).cancel(TRANSFER_RESULT_NOTIFICATION_ID)
    service = autoclass(TRANSFER_SERVICE_CLASS)
    intent = service.getDefaultIntent(
        context,
        "",
        "MoonTransfer",
        description,
        session_id,
    )
    build_version = autoclass("android.os.Build$VERSION")
    _start_service_intent(context, intent, int(build_version.SDK_INT))


def _start_service_intent(context: Any, intent: Any, sdk_int: int) -> None:
    try:
        if sdk_int >= 26:
            context.startForegroundService(intent)
        else:
            context.startService(intent)
    except Exception as error:
        raise AndroidRuntimeError(
            "Android non ha consentito l'avvio del trasferimento in background. "
            "Mantieni MoonTransfer visibile in primo piano e riprova. Se il "
            "problema persiste, il limite temporale di sistema per i "
            "trasferimenti potrebbe essere esaurito."
        ) from error


def stop_transfer_service() -> None:
    try:
        from jnius import autoclass
    except ImportError as error:
        raise AndroidRuntimeError("Runtime Android non disponibile.") from error

    context = android_context()
    service = autoclass(TRANSFER_SERVICE_CLASS)
    service.stop(context)


def parse_content_uri(value: str) -> Any:
    try:
        from jnius import autoclass
    except ImportError as error:
        raise AndroidRuntimeError("Runtime Android non disponibile.") from error
    return autoclass("android.net.Uri").parse(value)


def update_transfer_notification(notification: TransferNotification) -> None:
    _post_notification(
        TRANSFER_SERVICE_ID,
        notification,
        ongoing=True,
        auto_cancel=False,
    )


def post_transfer_result_notification(
    notification: TransferNotification,
) -> None:
    _post_notification(
        TRANSFER_RESULT_NOTIFICATION_ID,
        notification,
        ongoing=False,
        auto_cancel=True,
    )


def _post_notification(
    notification_id: int,
    notification: TransferNotification,
    *,
    ongoing: bool,
    auto_cancel: bool,
) -> None:
    try:
        from jnius import autoclass
    except ImportError as error:
        raise AndroidRuntimeError("Runtime Android non disponibile.") from error

    context = android_context()
    notification_class = autoclass("android.app.Notification")
    builder_class = autoclass("android.app.Notification$Builder")
    pending_intent = _application_pending_intent(context)
    cancel_pending_intent = (
        _cancel_transfer_pending_intent(
            context,
            notification.cancel_session_id,
        )
        if ongoing and notification.cancel_session_id is not None
        else None
    )
    builder = _notification_builder(
        context,
        notification_class,
        builder_class,
    )
    _configure_notification_builder(
        builder,
        notification_class,
        notification,
        pending_intent,
        cancel_pending_intent,
        context,
        ongoing=ongoing,
        auto_cancel=auto_cancel,
    )

    public_builder = _notification_builder(
        context,
        notification_class,
        builder_class,
    )
    public_builder.setContentTitle("MoonTransfer")
    public_builder.setContentText(notification.public_text)
    public_builder.setContentIntent(pending_intent)
    public_builder.setSmallIcon(context.getApplicationInfo().icon)
    public_builder.setVisibility(notification_class.VISIBILITY_PUBLIC)
    builder.setPublicVersion(public_builder.build())

    _notification_manager(context).notify(notification_id, builder.build())


def _notification_manager(context: Any) -> Any:
    try:
        from jnius import autoclass
    except ImportError as error:
        raise AndroidRuntimeError("Runtime Android non disponibile.") from error
    context_class = autoclass("android.content.Context")
    return context.getSystemService(context_class.NOTIFICATION_SERVICE)


def _application_pending_intent(context: Any) -> Any:
    try:
        from jnius import autoclass
    except ImportError as error:
        raise AndroidRuntimeError("Runtime Android non disponibile.") from error
    pending_intent_class = autoclass("android.app.PendingIntent")
    intent_class = autoclass("android.content.Intent")
    activity_class = autoclass("org.kivy.android.PythonActivity")
    intent = intent_class(context, activity_class)
    return pending_intent_class.getActivity(
        context,
        0,
        intent,
        pending_intent_class.FLAG_IMMUTABLE
        | pending_intent_class.FLAG_UPDATE_CURRENT,
    )


def _cancel_transfer_pending_intent(context: Any, session_id: str) -> Any:
    if not TRANSFER_SESSION_RE.fullmatch(session_id):
        raise AndroidRuntimeError("Sessione di annullamento non valida.")
    try:
        from jnius import autoclass
    except ImportError as error:
        raise AndroidRuntimeError("Runtime Android non disponibile.") from error

    pending_intent_class = autoclass("android.app.PendingIntent")
    intent_class = autoclass("android.content.Intent")
    uri_class = autoclass("android.net.Uri")
    service_class = autoclass(TRANSFER_SERVICE_CLASS)
    intent = intent_class(context, service_class)
    intent.setAction(TRANSFER_CANCEL_ACTION)
    intent.setData(uri_class.parse(f"moontransfer://cancel/{session_id}"))
    intent.putExtra(TRANSFER_SESSION_EXTRA, session_id)
    request_code = int(session_id[:8], 16) & 0x7FFFFFFF
    return pending_intent_class.getService(
        context,
        request_code,
        intent,
        pending_intent_class.FLAG_IMMUTABLE
        | pending_intent_class.FLAG_CANCEL_CURRENT,
    )


def _notification_builder(
    context: Any,
    notification_class: Any,
    builder_class: Any,
) -> Any:
    try:
        from jnius import autoclass
    except ImportError as error:
        raise AndroidRuntimeError("Runtime Android non disponibile.") from error
    build_version = autoclass("android.os.Build$VERSION")
    if int(build_version.SDK_INT) >= 26:
        return builder_class(
            context,
            TRANSFER_NOTIFICATION_CHANNEL,
        )
    builder = builder_class(context)
    builder.setPriority(notification_class.PRIORITY_LOW)
    return builder


def _configure_notification_builder(
    builder: Any,
    notification_class: Any,
    notification: TransferNotification,
    pending_intent: Any,
    cancel_pending_intent: Any | None,
    context: Any,
    *,
    ongoing: bool,
    auto_cancel: bool,
) -> None:
    builder.setContentTitle(notification.title)
    builder.setContentText(notification.text)
    builder.setContentIntent(pending_intent)
    builder.setOngoing(ongoing)
    builder.setAutoCancel(auto_cancel)
    builder.setOnlyAlertOnce(ongoing)
    builder.setSmallIcon(context.getApplicationInfo().icon)
    builder.setVisibility(notification_class.VISIBILITY_PRIVATE)
    if ongoing:
        builder.setCategory(notification_class.CATEGORY_PROGRESS)
    if cancel_pending_intent is not None:
        builder.addAction(
            context.getApplicationInfo().icon,
            "Interrompi",
            cancel_pending_intent,
        )
    if notification.indeterminate:
        builder.setProgress(0, 0, True)
    elif notification.progress is not None:
        builder.setProgress(100, notification.progress, False)
    else:
        builder.setProgress(0, 0, False)

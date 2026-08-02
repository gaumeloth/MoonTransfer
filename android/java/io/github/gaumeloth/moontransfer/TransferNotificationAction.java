package io.github.gaumeloth.moontransfer;

import android.app.Notification;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;

public final class TransferNotificationAction {
    static final String ACTION_CANCEL_TRANSFER =
            "io.github.gaumeloth.moontransfer.action.CANCEL_TRANSFER";
    static final String EXTRA_SESSION_ID =
            "io.github.gaumeloth.moontransfer.extra.SESSION_ID";

    private TransferNotificationAction() {
    }

    public static void addCancelAction(
            Notification.Builder builder,
            Context context,
            String sessionId
    ) {
        if (!TransferControl.isValidSessionId(sessionId)) {
            throw new IllegalArgumentException("Invalid transfer session");
        }

        Intent intent = new Intent();
        intent.setClassName(
                context,
                context.getPackageName() + ".ServiceTransfer"
        );
        intent.setAction(ACTION_CANCEL_TRANSFER);
        intent.setData(Uri.parse("moontransfer://cancel/" + sessionId));
        intent.putExtra(EXTRA_SESSION_ID, sessionId);

        int requestCode = (int) (
                Long.parseLong(sessionId.substring(0, 8), 16)
                & 0x7fffffffL
        );
        PendingIntent pendingIntent = PendingIntent.getService(
                context,
                requestCode,
                intent,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_CANCEL_CURRENT
        );
        builder.addAction(
                context.getApplicationInfo().icon,
                "Interrompi",
                pendingIntent
        );
    }
}

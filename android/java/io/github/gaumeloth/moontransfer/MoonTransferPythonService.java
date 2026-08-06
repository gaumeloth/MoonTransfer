package io.github.gaumeloth.moontransfer;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import org.kivy.android.PythonActivity;
import org.kivy.android.PythonService;

public class MoonTransferPythonService extends PythonService {
    private static final String TAG = "MoonTransferService";
    private static final long TIMEOUT_STOP_DELAY_MS = 2000L;
    public static final String NOTIFICATION_CHANNEL_ID =
            "io.github.gaumeloth.moontransfer.transfers";

    private volatile String activeSessionId;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) {
            Log.w(TAG, "Ignoring a sticky restart without a transfer session");
            stopSelf(startId);
            return START_NOT_STICKY;
        }

        if (TransferNotificationAction.ACTION_CANCEL_TRANSFER.equals(
                intent.getAction()
        )) {
            String requestedSession = intent.getStringExtra(
                    TransferNotificationAction.EXTRA_SESSION_ID
            );
            if (
                    requestedSession != null
                    && requestedSession.equals(activeSessionId)
                    && TransferControl.requestCancel(
                            getApplicationContext(),
                            requestedSession
                    )
            ) {
                Log.i(TAG, "Transfer cancellation requested from notification");
            } else {
                Log.w(TAG, "Ignoring cancellation for an inactive session");
            }
            return startType();
        }

        String sessionId = intent.getStringExtra("pythonServiceArgument");
        if (!TransferControl.isValidSessionId(sessionId)) {
            Log.e(TAG, "Refusing to start without a valid transfer session");
            stopSelf(startId);
            return START_NOT_STICKY;
        }
        activeSessionId = sessionId;
        return super.onStartCommand(intent, flags, startId);
    }

    @Override
    protected void doStartForeground(Bundle extras) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            super.doStartForeground(extras);
            return;
        }

        Context context = getApplicationContext();
        NotificationManager manager = (NotificationManager) context
                .getSystemService(Context.NOTIFICATION_SERVICE);
        NotificationChannel channel = new NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                "Trasferimenti MoonTransfer",
                NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription("Stato dei trasferimenti di file in corso");
        channel.setLockscreenVisibility(Notification.VISIBILITY_PRIVATE);
        manager.createNotificationChannel(channel);

        Intent activityIntent = new Intent(context, PythonActivity.class);
        PendingIntent pendingIntent = PendingIntent.getActivity(
                context,
                0,
                activityIntent,
                PendingIntent.FLAG_IMMUTABLE
                        | PendingIntent.FLAG_UPDATE_CURRENT
        );
        Notification notification = new Notification.Builder(
                context,
                NOTIFICATION_CHANNEL_ID
        )
                .setContentTitle(extras.getString("contentTitle"))
                .setContentText(extras.getString("contentText"))
                .setContentIntent(pendingIntent)
                .setSmallIcon(context.getApplicationInfo().icon)
                .setCategory(Notification.CATEGORY_PROGRESS)
                .setOnlyAlertOnce(true)
                .setOngoing(true)
                .build();
        startForeground(getServiceId(), notification);
    }

    @Override
    public void onTimeout(int startId, int fgsType) {
        Log.w(TAG, "Foreground transfer reached the Android time limit");
        TransferControl.requestCancel(getApplicationContext(), activeSessionId);
        stopForeground(STOP_FOREGROUND_REMOVE);
        new Handler(Looper.getMainLooper()).postDelayed(
                () -> stopSelf(startId),
                TIMEOUT_STOP_DELAY_MS
        );
    }
}

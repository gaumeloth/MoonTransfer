package io.github.gaumeloth.moontransfer;

import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import org.kivy.android.PythonService;

public class MoonTransferPythonService extends PythonService {
    private static final String TAG = "MoonTransferService";
    private static final long TIMEOUT_STOP_DELAY_MS = 2000L;

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

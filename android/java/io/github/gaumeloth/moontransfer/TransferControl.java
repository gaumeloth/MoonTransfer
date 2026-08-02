package io.github.gaumeloth.moontransfer;

import android.content.Context;
import android.util.Log;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.regex.Pattern;

final class TransferControl {
    private static final String TAG = "MoonTransferService";
    private static final Pattern SESSION_ID = Pattern.compile("^[0-9a-f]{32}$");

    private TransferControl() {
    }

    static boolean isValidSessionId(String value) {
        return value != null && SESSION_ID.matcher(value).matches();
    }

    static boolean requestCancel(Context context, String sessionId) {
        if (!isValidSessionId(sessionId)) {
            return false;
        }

        File temporary = null;
        try {
            File serviceRoot = new File(
                    context.getFilesDir(),
                    "transfer-cache/transfer-service"
            ).getCanonicalFile();
            File session = new File(serviceRoot, sessionId).getCanonicalFile();
            if (!serviceRoot.equals(session.getParentFile())) {
                return false;
            }

            File commands = new File(session, "commands").getCanonicalFile();
            if (!session.equals(commands.getParentFile()) || !commands.isDirectory()) {
                return false;
            }

            JSONObject command = new JSONObject();
            command.put("version", 1);
            command.put("session_id", sessionId);
            command.put("command", "cancel");
            command.put("destination_uri", JSONObject.NULL);

            temporary = File.createTempFile(".cancel-", ".tmp", commands);
            try (FileOutputStream output = new FileOutputStream(temporary);
                 OutputStreamWriter writer = new OutputStreamWriter(
                         output,
                         StandardCharsets.UTF_8
                 )) {
                writer.write(command.toString());
                writer.flush();
                output.getFD().sync();
            }
            temporary.setReadable(false, false);
            temporary.setWritable(false, false);
            temporary.setReadable(true, true);
            temporary.setWritable(true, true);

            File destination = new File(
                    commands,
                    "cancel-" + System.nanoTime() + "-" + UUID.randomUUID() + ".json"
            );
            if (!temporary.renameTo(destination)) {
                return false;
            }
            destination.setReadable(false, false);
            destination.setWritable(false, false);
            destination.setReadable(true, true);
            destination.setWritable(true, true);
            temporary = null;
            return true;
        } catch (Exception error) {
            Log.e(TAG, "Unable to request transfer cancellation", error);
            return false;
        } finally {
            if (temporary != null && temporary.exists() && !temporary.delete()) {
                Log.w(TAG, "Unable to remove a temporary control file");
            }
        }
    }
}

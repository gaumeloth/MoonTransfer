package io.github.gaumeloth.moontransfer;

import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.widget.Toast;
import java.util.ArrayList;
import org.kivy.android.PythonActivity;

public class MoonTransferActivity extends PythonActivity {
    private static final String PENDING = "moontransfer.pendingShares";
    private final ArrayList<Intent> pendingShares = new ArrayList<>();

    @Override
    public void onCreate(Bundle state) {
        // Capture before Python starts; onNewIntent can also arrive during startup.
        if (state != null) {
            ArrayList<Intent> restored = state.getParcelableArrayList(PENDING);
            if (restored != null) pendingShares.addAll(restored);
        } else {
            enqueueShare(getIntent());
        }
        super.onCreate(state);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        enqueueShare(intent);
    }

    private synchronized void enqueueShare(Intent intent) {
        if (intent == null || (intent.getFlags() & Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY) != 0) return;
        String action = intent.getAction();
        if (!Intent.ACTION_SEND.equals(action) && !Intent.ACTION_SEND_MULTIPLE.equals(action)) return;
        if (pendingShares.size() >= 8) {
            Toast.makeText(this, "Troppe condivisioni. Riprova tra poco.", Toast.LENGTH_LONG).show();
            return;
        }
        pendingShares.add(new Intent(intent));
    }

    public synchronized Intent consumeSharedIntent() {
        return pendingShares.isEmpty() ? null : pendingShares.remove(0);
    }

    public void shareTransferCode(String message) {
        runOnUiThread(() -> {
            try {
                Intent intent = new Intent(Intent.ACTION_SEND);
                intent.setType("text/plain");
                intent.putExtra(Intent.EXTRA_TEXT, message);
                startActivity(Intent.createChooser(intent, null));
            } catch (Exception error) {
                Toast.makeText(this, "Condivisione del codice non disponibile", Toast.LENGTH_LONG).show();
            }
        });
    }

    public void openSavedDocument(String value, boolean share, boolean directory) {
        runOnUiThread(() -> {
            try {
                Uri document = Uri.parse(value);
                if (!"content".equals(document.getScheme())
                        || document.getAuthority() == null
                        || document.getAuthority().isEmpty()
                        || (share && directory)) {
                    throw new IllegalArgumentException("Invalid document action");
                }
                String mime = getContentResolver().getType(document);
                if (mime == null) {
                    mime = directory ? "vnd.android.document/directory" : "application/octet-stream";
                }
                Intent intent = new Intent(share ? Intent.ACTION_SEND : Intent.ACTION_VIEW);
                if (share) {
                    intent.setType(mime);
                    intent.putExtra(Intent.EXTRA_STREAM, document);
                } else {
                    intent.setDataAndType(document, mime);
                }
                intent.setClipData(ClipData.newRawUri("MoonTransfer", document));
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                // Keep overloaded Android calls on the Java side of the bridge.
                startActivity(Intent.createChooser(intent, null));
            } catch (ActivityNotFoundException error) {
                Toast.makeText(this, "Nessuna app compatibile per questo contenuto", Toast.LENGTH_LONG).show();
            } catch (SecurityException error) {
                Toast.makeText(this, "Accesso al documento non disponibile o revocato", Toast.LENGTH_LONG).show();
            } catch (Exception error) {
                Toast.makeText(this, "Impossibile aprire o condividere il documento salvato", Toast.LENGTH_LONG).show();
            }
        });
    }

    @Override
    protected synchronized void onSaveInstanceState(Bundle state) {
        state.putParcelableArrayList(PENDING, new ArrayList<>(pendingShares));
        super.onSaveInstanceState(state);
    }
}

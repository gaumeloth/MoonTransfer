# MoonTransfer Android experiment

Italian version: [README.it.md](README.it.md)

This directory contains an isolated Kivy and Buildozer environment for the
Android feasibility prototype. It does not replace the PySide6 desktop
application and is not part of desktop release artifacts.

## Current scope

The prototype currently provides:

- a Python 3.13 and Kivy 2.3.1 development environment;
- a Kivy interface with separate send and receive views for one file;
- generated Android build sources containing only explicitly approved,
  Qt-independent MoonTransfer modules;
- a pinned Buildozer and python-for-android configuration;
- an `arm64-v8a` debug APK target;
- a private recipe that verifies and cross-compiles the pinned `croc` source;
- an Android runtime probe that locates the packaged executable and checks its
  version without exposing a transfer secret;
- an embedded build identity shown in the header and in a copyable information
  dialog, including the source commit, bundled `croc`, protocol, Python runtime,
  and platform without transfer codes or local paths;
- source selection and verified destination saving through Android's Storage
  Access Framework (SAF);
- Android-to-desktop sending and desktop-to-Android receiving compatible with
  MoonTransfer protocol v2;
- proposal review with filename, size and SHA-256 before download;
- acceptance and rejection through the prompted main `croc` connection;
- a `dataSync` foreground service that owns the active `croc` process and keeps
  transfers running while the user switches to another application;
- a private, state-aware foreground notification with transfer phase, filename,
  byte progress, current speed and estimated remaining time when available,
  a session-bound **Interrompi** (Stop) action, and a dismissible completion,
  rejection or failure notification;
- transfer progress, cancellation, inactivity and decision timeouts, integrity
  verification and cleanup of private temporary files.

This remains an experimental single-file client. It cannot select or receive
multiple files or folders, resume an interrupted transfer, or build release
artifacts for architectures other than `arm64-v8a`. It declares `INTERNET`, the
foreground-service permissions required for `dataSync`, and the notification
permission used to show transfer status. The lock-screen public version of that
notification is deliberately generic: transfer codes, hashes, paths, content
URIs and technical errors are never displayed there. SAF grants access only to
documents explicitly chosen by the user; no broad storage permission is
requested.

## Transport compatibility

> [!IMPORTANT]
> The current Android recipe builds `croc 11.0.1`. An APK produced from this
> source cannot transfer data to or from desktop builds or older experimental
> APKs based on `croc 10.x`. Build or update both endpoints together and, for
> testing, use the same repository revision on both devices.

The relevant versions are:

| MoonTransfer build | Bundled `croc` | Compatible with the current Android APK |
| --- | --- | --- |
| Desktop `v0.1.0-alpha.1` | `10.4.13` | No |
| Desktop `v0.1.0-alpha.2` and older prototype APKs | `10.7.0` | No |
| Desktop `v0.1.0-alpha.3`, current source, and Android recipe | `11.0.1` | Yes |

For compatibility tests, rebuild the APK from the intended revision and check
that its green transport probe reports `croc 11.0.1`. Do not use an old debug
APK with a current desktop build, or a current APK with the pre-`croc 11`
desktop alphas. This boundary is independent of the operating system and CPU
architecture.

`croc 11` introduced version 2 of its PAKE wire protocol and intentionally
rejects the earlier handshake. It binds key establishment to the peers, roles,
session, room and transcript, strengthens key derivation and salt handling,
and adds mutual key confirmation. There is no compatibility fallback because
using one would discard those security properties. See the official [`croc
11.0.0` release notes](https://github.com/schollz/croc/releases/tag/v11.0.0)
and the upstream [security
upgrade](https://github.com/schollz/croc/pull/1212).

A mixed `croc 10`/`croc 11` pair fails while securing the channel, before the
MoonTransfer metadata manifest or main payload is transferred. The technical
details may report an unsupported PAKE protocol version or the generic `could
not secure channel` error. This is the expected compatibility failure; it does
not indicate an Android storage or foreground-service problem.

## Host prerequisites

Android builds require Linux or macOS. The current configuration expects Java
17, Go 1.25 or newer, the standard native build tools and Rust. Buildozer
downloads the configured Android SDK and NDK when necessary.

On Ubuntu, install the system prerequisites before building:

```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk autoconf libtool \
  pkg-config cmake libffi-dev libssl-dev automake autopoint gettext \
  make gcc g++
```

On Arch Linux and derivatives such as Garuda Linux:

```bash
sudo pacman -S --needed git zip unzip jdk17-openjdk autoconf libtool \
  pkgconf cmake libffi openssl automake gettext make gcc go
```

Install Rust with the method documented at <https://rustup.rs/> and make sure
`cargo` and `rustc` are available on `PATH`.

Install Go 1.25 or newer from <https://go.dev/doc/install> if the package
provided by the host operating system is older. The Android recipe deliberately
uses the installed toolchain instead of downloading a different Go version
implicitly.

The Android toolchain is validated with Java 17. If another Java release is the
system default, select Java 17 for a single invocation without changing the
global default:

```bash
JAVA_HOME=/usr/lib/jvm/java-17-openjdk ./scripts/android.sh doctor
JAVA_HOME=/usr/lib/jvm/java-17-openjdk ./scripts/android.sh build
```

## Commands

Run these commands from the repository root:

```bash
./scripts/android.sh doctor
./scripts/android.sh prepare
./scripts/android.sh run
./scripts/android.sh build
```

`doctor` checks host-side prerequisites, including Java and Go versions.
`prepare` recreates the generated source tree under `build/android/source`.
`run` launches the Kivy scaffold on the desktop for a quick UI smoke test.
`build` produces a debug APK under `dist/android`.

The preparation step also embeds `build-info.json`. A clean checkout at an
exact pre-release tag uses that displayed version; otherwise the APK shows a
development version with the current commit prefix. The information button in
the header opens the full copyable diagnostic summary.

When the APK starts on Android, it resolves `libcroc.so` from the application's
native library directory and runs `croc --version` in a worker thread. A green
status confirms that the transport executable can be started on the device.

The first invocation can download Python packages, Android tooling and source
archives. Generated source and build output must not be edited or committed.

## Test transfers with the desktop application

These are manual compatibility tests for the Android prototype, not an end-user
release procedure.

1. Build the current desktop application and Android debug APK from the same
   revision.
2. Install the generated `dist/android/moontransfer-<version>-arm64-v8a-debug.apk`
   on an ARM64 Android device.

### Send from Android to desktop

1. Start MoonTransfer on the desktop, open **Ricevi** (Receive), and choose a
   destination directory.
2. Start the Android app and wait for the green `croc` transport status.
3. In **Invia** (Send), press **Seleziona file** (Select file) and choose a small,
   non-sensitive document from the Android system picker.
4. Check the displayed name and size, then press **Prepara e invia** (Prepare
   and send).
5. The app hashes the private staged copy and displays a 32-character code. The
   code is also copied to the Android clipboard.
6. Switch to the messaging application used to communicate the code. Leave
   MoonTransfer in the background while the receiver enters it; the ongoing
   transfer notification must remain visible and identify the current phase.
7. Enter that code in the desktop **Ricevi** tab and start receiving.
8. Check the filename, size and SHA-256 information shown by the desktop app,
   then accept or reject the transfer.
9. If accepted, both applications should report progress and completion. Check
   that the verified file appears in the chosen desktop destination. If
   rejected, Android should report the receiver's decision without sending the
   main payload.
10. Return to MoonTransfer and verify that a new file can be selected and a new
    transfer started without closing or restarting the application.

### Receive from desktop on Android

1. Start MoonTransfer on the desktop, open **Invia** (Send), and choose one
   small, non-sensitive file.
2. Start the Android app, open **Ricevi** (Receive), enter the code shown by the
   desktop application, and press **Ricevi informazioni** (Receive information).
3. Check the filename, size and SHA-256 shown on Android.
4. Press **Rifiuta** (Reject) to notify the desktop sender without downloading
   the payload, or **Accetta** (Accept) to continue.
5. After an accepted file has been downloaded into private storage and its
   manifest has been verified, Android opens the system save picker.
6. Choose the final name and location. The system picker handles any existing
   file confirmation; MoonTransfer does not open that destination before
   verification succeeds.
7. Check that both applications report completion and that the saved file is
   available through the selected Android document provider.
8. Verify that the code field and transfer controls are usable again without
   closing or restarting MoonTransfer.

### Lifecycle and recovery checks

Before treating an Android change as manually validated, also exercise these
cases with a small, non-sensitive file:

1. Start a send, wait for the code, press Home or switch to the messaging app,
   then reopen MoonTransfer. The notification must remain available and the GUI
   must reconnect to the same phase without starting another transfer.
2. While a transfer is active, remove MoonTransfer from the recent-apps screen
   and reopen it. Controls that could start a second operation must remain
   disabled until the existing service finishes or is cancelled.
3. Rotate the device during metadata exchange, payload transfer and the
   receiver decision. Activity recreation must not duplicate `croc`, lose the
   proposal or unlock conflicting controls.
4. Cancel the source picker before choosing a file. Separately, cancel the save
   picker after a verified receive, then reopen it with **Scegli dove salvare**
   (Choose where to save). Both paths must return to usable controls.
5. Cancel one active transfer with the in-app **Interrompi** action and another
   with the notification action. Both must stop the same current session and
   leave no permanently blocked GUI state.
6. After completion, rejection and cancellation, start another transfer in
   both directions without restarting the application.
7. As a destructive recovery test, use Android **Force stop** during a transfer
   and reopen the app. After the bounded recovery grace period, MoonTransfer
   must report the abandoned session, remove it and unlock the controls rather
   than remaining attached indefinitely.
8. On Android 13 or later, repeat a small transfer after denying notification
   permission. The transfer must either start under the platform's foreground-
   service rules or fail with a visible explanation; it must not silently leave
   an active or blocked session.

If the save picker is cancelled, the verified private copy remains available
while the foreground transfer service remains active. Press **Scegli dove
salvare** (Choose where to save) to retry, or **Interrompi** (Stop) to discard
it.

Pressing Home or switching applications does not cancel an active operation:
the foreground service continues it and the GUI reconnects to the persisted
session when reopened. **Interrompi** sends a cancellation command to that
service. The service is sticky, and removing MoonTransfer from the recent-apps
screen does not intentionally stop it. Android **Force stop**, a device restart,
or the operating system actually terminating the service process can still
interrupt the operation; interrupted transfers are not resumed automatically.
When reopening, the GUI first reconnects to the persisted service request and
briefly tolerates a state snapshot that is temporarily unavailable. While a
service client is attached, controls cannot start a conflicting operation even
before the first valid snapshot arrives. If the snapshot remains unreadable or
the service heartbeat remains unchanged for about 15 seconds, MoonTransfer
reports the failure, stops any stale service instance, removes the abandoned
private session and unlocks the controls instead of waiting indefinitely.

The ongoing notification uses an indeterminate bar while MoonTransfer is
preparing metadata, connecting or verifying, no bar while it is waiting for a
decision, and a determinate bar during payload transfer and final SAF saving.
When `croc` supplies enough data, its compact status also shows transferred and
total bytes, current speed and estimated remaining time. Tapping the notification
opens MoonTransfer; **Interrompi** requests cancellation without reopening the
activity. The action is available only on the private notification for the
active session. The generic lock-screen version and terminal result
notifications do not expose it. The foreground notification is removed with
the service; completion, rejection and failure leave a separate dismissible
result notification. User-requested cancellation does not leave a result
notification.

## Android transfer design

The system picker returns a content URI rather than a normal filesystem path.
MoonTransfer queries its portable filename and optional size, opens the URI
through `ContentResolver`, and copies it into a fresh app-private directory with
mode `0600`. The private copy is the controlled source used for hashing and by
`croc`; its fingerprint is checked again before the main sender starts. It is
removed after completion, rejection, failure or cancellation. Stale app-owned
staging and session directories are removed on the next start only when no
foreground transfer is active.

The Kivy activity does not own the transfer controller or the `croc` child
process. After validating the user action, it creates a private session and
starts a sticky foreground service of type `dataSync`; that separate process
owns the controller for the whole transfer and is not stopped merely because
the activity task is removed. The activity and service exchange versioned JSON
snapshots and one-shot commands through app-private files written atomically
with restrictive permissions. Only a random session identifier is placed in
the Android service intent; transfer codes, document paths, state and
destination content URIs stay in app-private storage. Recreating the activity
therefore reconstructs the visible state without restarting `croc` or deleting
an active staging directory. Recovery discovers the newest valid request before
reading its snapshot, so a temporarily missing or unreadable state file is not
mistaken immediately for the absence of a transfer. Each snapshot is accepted
only when its session, operation and terminal flag are consistent with the
request and the Android state machine. The connected service client itself
keeps conflicting controls disabled. Separate 15-second grace periods for an
unreadable snapshot and an unchanged heartbeat tolerate short scheduling or
filesystem stalls while still bounding recovery from a terminated service
process.

The repository-owned service class rejects an Android sticky restart that does
not identify a valid session. On Android 15 and later it also handles the
platform `dataSync` timeout by requesting cancellation, leaving foreground mode
and stopping the service within the required grace period. Android limits this
service type to six hours of background execution in each rolling 24-hour
period, shared by the application's `dataSync` services; bringing the app to the
foreground resets that allowance. If Android refuses a new foreground-service
start, MoonTransfer reports that the app must remain visible and the user must
retry. See the official [foreground-service timeout
documentation](https://developer.android.com/develop/background-work/services/fgs/timeout).

The service derives notification content from the same in-memory state that it
writes to the private session snapshot. Progress-driven notification updates
are limited to approximately one per second to avoid unnecessary system work;
state changes and terminal results are delivered immediately. The detailed
notification is marked private and has a generic public lock-screen version.
Neither notification includes transfer secrets, SHA-256 values, filesystem
paths, content URIs, relay addresses or raw process errors. The **Interrompi**
action uses an explicit immutable `PendingIntent` containing only the random
session identifier. The service accepts it only when that identifier matches
the active session, then writes the same restricted, app-private cancellation
command used by the GUI.

The sender then reuses the desktop protocol instead of sending a raw `croc`
payload:

1. scan the staged file and calculate SHA-256;
2. create a protocol-v2 proposal containing a separately generated main-payload
   code;
3. send the bounded JSON manifest with the single user-facing code;
4. after the desktop receives the manifest, start the main `croc send` process;
5. let the prompted desktop receiver communicate acceptance or rejection
   through the main `croc` connection.

The Android receiver follows the inverse flow:

1. receive the bounded manifest into an isolated app-private directory;
2. validate every protocol field and reject unsupported multi-item payloads;
3. show the single file's portable name, declared size and SHA-256 before
   downloading it;
4. start the prompted main receiver and write `y` or `n` to `croc` so the
   desktop sender receives a protocol-level acceptance or rejection;
5. for accepted transfers, check private free space and enforce the declared
   byte limit while receiving;
6. verify the exact received tree, size and SHA-256 against the manifest;
7. only after verification, launch Android's `ACTION_CREATE_DOCUMENT` picker
   and copy the verified file to the returned content URI;
8. remove the manifest and private payload after completion, rejection,
   cancellation or failure.

Cancelling the system save picker does not discard the verified private copy;
the user can reopen it while the service remains active, or cancel the transfer
to discard it. This ordering avoids touching an existing destination before
integrity checks have passed. The system document provider remains responsible
for final name conflicts and overwrite confirmation.

Both secrets are passed in `CROC_SECRET`, never as command-line arguments.
Each session receives an isolated `croc` configuration directory. Process
output is consumed concurrently from stdout and stderr, bounded per record and
redacted before callbacks receive it. Process completion is determined from the
exit status; textual output is parsed only for progress and rejection-oriented
status. A 15-minute inactivity timeout is reset whenever `croc` emits output,
so it does not impose a fixed maximum duration on an active transfer. A
separate 15-minute decision timeout automatically rejects an unanswered
proposal instead of leaving the desktop sender waiting indefinitely. Only one
send or receive operation can run at a time.

## Isolation from desktop releases

Android dependencies live in this directory's own `pyproject.toml` and
`uv.lock`. The root project keeps PySide6 as its only GUI runtime. Buildozer
receives a generated source tree, while `MoonTransfer.spec` continues to package
`src/moontransfer/app.py` for desktop systems.

The Android main-screen widget hierarchy and static styling live in
`app/moontransfer_android/moontransfer.kv`. `application.py` loads that file,
validates every required widget identifier and binds events in Python. The KV
file remains declarative: transfer state, lifecycle recovery, service commands
and user actions stay in Python rather than being embedded in presentation
expressions.

The generated package intentionally excludes these Qt-specific modules:

- `app.py`;
- `desktop.py`;
- `runner.py`;
- `tasks.py`;
- `transfer.py`;
- `widgets.py`.

Shared modules are copied from `src/moontransfer` on every preparation, so the
Android prototype cannot silently retain an outdated copy of the protocol.

## Native croc build

The local recipe under `recipes/croc` pins the same `croc` version declared by
the desktop project. It verifies the upstream source archive with SHA-512 and
builds a position-independent ARM64 Android executable with cgo enabled. This
lets Go delegate relay hostname resolution to Android's native DNS resolver, so
the app respects the active network, VPN, and Private DNS configuration. The
executable is packaged as `lib/arm64-v8a/libcroc.so`, which keeps it inside the
APK's signed native-library area. The upstream MIT license is also included in
the application package. The Android build command fingerprints this recipe;
when its version, checksum, or build logic changes, it removes the stale native
`croc` cache and rebuilds the distribution instead of silently reusing an old
executable.

## Known limitations

- only single-file sending and receiving are implemented on Android;
- directory and multiple-file payloads are not implemented and incoming ones
  are rejected before the main payload is downloaded;
- the final SAF copy cannot be made atomically across every third-party document
  provider; interruption during that local copy can leave a partial destination;
- background execution is protected while the app is covered, the user switches
  applications, or its task is removed from the recent-apps screen, but
  force-stopping the app, restarting the device, or a service/process failure
  still ends the transfer;
- Android 15 and later impose a shared six-hour `dataSync` foreground-service
  allowance while the app is in the background; reaching it cancels the active
  transfer, and starting another one may be refused until the allowance resets;
- interrupted transfers cannot yet be resumed from a partial payload;
- only a debug `arm64-v8a` APK is produced;
- transfer status still depends partly on human-readable `croc` output because
  `croc` does not expose a structured progress API.

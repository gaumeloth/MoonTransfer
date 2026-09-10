# MoonTransfer for Android

Italian version: [README.it.md](README.it.md)

This directory contains an isolated Kivy and Buildozer environment for the
Android feasibility prototype. It does not replace the PySide6 desktop
application. Build dependencies remain isolated, while the signed APK is a
separate asset in the same draft releases as the desktop packages.

[Main guide](../README.md) | [Troubleshooting](../docs/TROUBLESHOOTING.md) | [APK signing](SIGNING.md)

## Contents

- [Installation and first start](#installation-and-first-start)
- [Current scope](#current-scope)
- [Android system sharing](#android-system-sharing)
- [Results and recovery](#results-and-recovery)
- [Transport compatibility](#transport-compatibility)
- [Host prerequisites](#host-prerequisites)
- [Commands](#commands)
- [Continuous integration artifact](#continuous-integration-artifact)
- [Test transfers with the desktop application](#test-transfers-with-the-desktop-application)
- [Android transfer design](#android-transfer-design)
- [Isolation from desktop builds](#isolation-from-desktop-builds)
- [Native croc build](#native-croc-build)
- [Known limitations](#known-limitations)
- [Local GUI tests](#local-gui-tests)

## Installation and first start

- Current APKs are **ARM64** (`arm64-v8a`) and require at least **Android 7.0 / API 24**. This is the declared minimum, not a claim of testing on every device.
- Use a physical ARM64 device to validate transfers and native integration. An x86_64 emulator advertising ARM64 through translation is not native execution: croc can fail even if the GUI starts.
- Download `MoonTransfer-0.1.0-alpha.4-android-arm64.apk` from the `alpha.4` [GitHub Release](https://github.com/gaumeloth/MoonTransfer/releases), together with `SHA256SUMS`, and verify the checksum before installing. In Actions artifacts choose `*-debug.apk` for debug or `*-android-arm64.apk` for a signed build, never `*-release-unsigned.apk`.
- Open the APK on the phone and allow installation from that source only if you trust the download. Before switching from debug to permanent signing, read [Installation transition](SIGNING.md#installation-transition): uninstalling deletes private data.
- At first start, check that no transport-unavailable warning remains. The top-right information button shows version, commit, croc and protocol.
- Allow notifications when prompted to monitor and stop background transfers. Files and destinations use Android's picker; unrestricted access to all storage is not required.

To start, choose **Invia > File / Cartella > Prepara invio**; communicate the code
with **Copia** or **Condividi**. On the receiver choose **Ricevi**, paste the code
or message and press **Verifica contenuto**. Inspect the contents before accepting;
after final verification choose where to save. Labels here match the Italian UI.

## Current scope

The prototype currently provides:

- a Python 3.13 and Kivy 2.3.1 development environment;
- a Kivy interface with separate send and receive views for files, folders, and
  mixed selections;
- generated Android build sources containing only explicitly approved,
  Qt-independent MoonTransfer modules;
- a pinned Buildozer and python-for-android configuration;
- an `arm64-v8a` debug APK target;
- a dedicated GitHub Actions workflow that tests, validates, and exposes a
  testable ARM64 debug APK for each relevant revision;
- a private recipe that verifies and cross-compiles the pinned `croc` source;
- an Android runtime probe that locates the packaged executable and checks its
  version without exposing a transfer secret;
- an embedded build identity available in a copyable information
  dialog, including the source commit, bundled `croc`, protocol, Python runtime,
  and platform without transfer codes or local paths;
- file and folder source selection, recursive private staging, and verified
  destination saving through Android's Storage Access Framework (SAF);
- Android-to-desktop sending and desktop-to-Android receiving compatible with
  MoonTransfer protocol v2;
- proposal review with top-level names, file and folder counts, total size, and
  SHA-256 information before download;
- acceptance and rejection through the prompted main `croc` connection;
- a `dataSync` foreground service that owns the active `croc` process and keeps
  transfers running while the user switches to another application;
- a private, state-aware foreground notification with transfer phase, filename,
  byte progress, current speed and estimated remaining time when available,
  a session-bound **Interrompi** (Stop) action, and a dismissible completion,
  rejection or failure notification;
- transfer progress, cancellation, inactivity and decision timeouts, integrity
  verification and cleanup of private temporary files.

This remains an experimental transfer client. It can build a mixed send
selection over multiple system-picker operations, display every staged
top-level file or folder, remove individual items, or clear the selection. It
cannot resume an interrupted transfer. Automatic builds produce ARM64 debug APKs;
an opt-in manual workflow can produce a signed release APK after the
[shared signing key is configured](SIGNING.md). Pre-release tags include the
signed APK in the same draft release as desktop builds. Other architectures
are not implemented.
The app declares `INTERNET`, the foreground-service permissions required for
`dataSync`, and the notification permission used to show transfer status. The
lock-screen public version of that notification is deliberately generic:
transfer codes, hashes, paths, content URIs and technical errors are never
displayed there. SAF grants access only to source documents, source folders, or
destination directories explicitly chosen by the user. External shares grant
temporary access to the supplied content URIs; no broad storage
permission is requested.

## Android system sharing

- **Condividi codice** opens the Android Sharesheet for the current transfer
  code. Copying the code remains available.
- In a gallery, file manager, or another app, use **Share > MoonTransfer** to
  import one or more files into the send selection. Existing selected items
  are preserved; sending still requires explicit confirmation.
- Share a received MoonTransfer code or the generated message from a chat to
  prefill **Ricevi**, provided the chat supports sharing text to other Android
  apps. Both the raw code and the app's spaced display format
  are recognized. Multiple distinct codes require sharing just one or entering
  it manually; replacing an existing code requires confirmation. Text without
  a recognized code is not imported as a file.
  Text lists and text in `ClipData` are also supported: duplicate codes are
  deduplicated, while distinct codes remain ambiguous. Accepted text has a
  combined limit of 8192 characters; shared files take precedence over any
  accompanying text.
- Alternatively, copy the entire message and paste it into **Ricevi**, using
  the paste button or the field's paste menu. Only the code is kept, including
  when it contains spaces or uppercase letters. Receiving still requires
  pressing **Verifica contenuto**. The paste button reports missing or multiple
  distinct codes and preserves the previous value; pasted directly into the
  field, these texts remain editable and do not enable verification.
  MoonTransfer's generated message includes this instruction, which also works
  in chats that do not support sharing text to other apps.
- External folders work when the sending provider supplies a readable document
  tree. A shared subdirectory is imported without including its parent tree.
  If access is unavailable, use **Seleziona cartella** to grant access through
  the system picker. File managers may instead share a ZIP or a flat file list;
  those are imported as supplied, without automatic extraction.
- New shares arriving during staging, a picker operation, or an active transfer
  are rejected with a request to retry afterward. They never start a second
  transfer or replace the active session.

The launcher uses `MoonTransferActivity`, a `singleTask` subclass of Kivy's
activity. A bounded native inbox captures startup and subsequent share intents
until Python can consume them. Saved activity state records the remaining inbox
so consumed shares are not replayed during restoration. Notification taps open
the same activity. Source access uses temporary URI grants and private staging;
no broad storage permission or messaging-app SDK is needed. If the process is
terminated during import, share the content again.

Manual checks on a physical Android device:

1. Share the code to a messaging app, return to MoonTransfer, and complete or
   cancel the transfer; also reopen it through its notification.
2. Share single and multiple files with MoonTransfer closed and already open.
   Verify selection contents and complete a transfer to a PC.
3. Share a raw code and the generated message; verify receive prefill, explicit
   start, replacement confirmation, and ambiguous/invalid text handling.
   Also copy the entire chat message and paste it using both the paste button
   and the field's paste menu: only the code should remain.
4. Share a supported folder/subfolder and test the picker fallback with a
   provider that cannot grant tree access.
5. Share during another operation, reopen from Recents, and rotate the device:
   check that no active session is replaced and no old share is imported twice.

QR codes are not implemented yet. See the next section for opening and
resharing received content.

## Results and recovery

After a verified save, **Apri** opens the saved document through Android and
**Condividi** shares a single saved file. Both use the public document URI with
a read grant, never a private staging path. Folder opening requires a compatible
document handler. Missing handlers or revoked access produce an error instead
of starting another transfer. The system save picker remembers its last URI
as an initial location, subject to provider support; it still asks for confirmation.

**Dettagli** in the incoming proposal lists paths, sizes and file hashes in
bounded pages. For multiple selected roots, the sender can set a portable
container name; an empty field uses `MoonTransfer`. Single roots keep their
original names. Older protocol-2 receivers ignore the optional container name.

A failed final save can be retried without receiving again, while the verified
private copy is retained for up to 15 minutes from verification in the active
service. Cancellation, timeout or service-process termination discards this
opportunity. Providers can leave partial destination documents after an error.

After sending, **Prepara nuovo invio** reuses the prepared copies with freshly
calculated hashes and new codes. Copies remain selectable for up to 15 minutes
after displaying the result, until app closure; originals are not re-imported.
Reselect them to include later edits. Explicit cancellation deletes the copies;
stale copies from killed processes are removed at the next startup. There is no
transfer history, queue or partial-download resume.

Manual checks: paste a full message on both platforms; send mixed roots with a
custom name; inspect proposal details; save/open/share a file; open a saved
folder; retry a failed provider save and confirm no second network reception;
prepare another send and check that its code differs. Repeat after cancelling
and reopening the save picker and after restarting the app.

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
| Desktop `v0.1.0-alpha.3`, `v0.1.0-alpha.4`, current source, and Android recipe | `11.0.1` | Yes |

For compatibility tests, rebuild the APK from the intended revision and check
in its information dialog that the bundled transport is `croc 11.0.1`. Do not use an old debug
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
  build-essential libltdl-dev libncurses5-dev libncursesw5-dev \
  libtinfo6 zlib1g-dev
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
./scripts/android.sh package
```

`doctor` checks host-side prerequisites, including Java and Go versions.
`prepare` recreates the generated source tree under `build/android/source`.
`run` launches the Kivy scaffold on the desktop for a quick UI smoke test.
`build` produces a debug APK under `dist/android`. After a successful build,
`package` validates its structure, native architecture, required application
files, and embedded identity, then stages a versioned copy under `release/`.
The wrapper always runs the locked Android environment with `uv run --frozen`,
so these commands never update `android/uv.lock` implicitly.

The preparation step also embeds `build-info.json`. A clean checkout at an
exact pre-release tag uses that displayed version; otherwise the APK shows a
development version with the current commit prefix. The information button in
the header opens the full copyable diagnostic summary.

When the APK starts on Android, it resolves `libcroc.so` from the application's
native library directory and runs `croc --version` in a worker thread.
A successful check confirms that the transport executable can start on the device.

The first invocation can download Python packages, Android tooling and source
archives. Generated source and build output must not be edited or committed.

## Continuous integration artifact

`.github/workflows/android-build.yml` runs on pull requests, pushes to `main`,
normal manual workflow dispatches, and reusable calls from the release workflow
(signed builds on pre-release tags). Its Ubuntu 24.04 job installs
pinned versions of `uv`, Python 3.13.14, Java 17, Go 1.25.12, and Rust 1.97.1,
verifies `android/uv.lock`, installs the locked build dependency group, runs
every `test_android*.py` test, executes `doctor`, and builds the `arm64-v8a`
debug APK.

A dedicated step also runs header, sharing, and scrolling GUI regression tests
with Kivy and software rendering, without ADB or an emulator. The decoded APK
manifest is checked for an enabled, exported share activity, `singleTask`
launch mode, and launcher, `ACTION_SEND`, and `ACTION_SEND_MULTIPLE` filters.
These checks do not replace manual testing with document providers and
messaging apps on a device.

The workflow selects the dedicated Buildozer `ci` profile. That profile accepts
the configured Android SDK licenses non-interactively while Buildozer installs
its isolated SDK and NDK. Normal local builds do not select the profile and
retain Buildozer's interactive license prompt.

The workflow caches downloaded Android SDK/NDK and Gradle data. It deliberately
does not cache the much larger python-for-android native build yet: this keeps
the first implementation easier to invalidate and audit, at the cost of a
slower clean build. That decision can be revisited after collecting timings and
cache reliability data from real runs.

Before upload, `package` verifies the APK as a ZIP archive, rejects duplicate or
unsafe paths and source-only `.xcf` assets, requires the expected ARM64 `croc`,
Python, and application libraries, checks the generated private application
files, and matches embedded version, commit, `croc`, and protocol metadata with
the requested build. Android's `aapt` then checks the application ID, version
name and code, SDK bounds, debug status, and declared native architecture. The
resulting raw
`MoonTransfer-<version>-android-arm64-debug.apk` is downloadable from the
workflow run summary for 14 days without an extra archive wrapper.

This file is only a test artifact. It is not attached to GitHub Releases and is
not signed with a project-controlled release key. Buildozer's debug signing
identity may differ between local and GitHub-hosted builds, so Android can
refuse an in-place update between them. Uninstalling the existing prototype
first resolves the signature mismatch, but also deletes its private app data.

The full build version and commit are embedded in `build-info.json`, and the
full version is used as Android's `versionName`. During the prototype phase the
debug `versionCode` stays at `1`. Release builds require an explicit versionCode
from 2 to 2100000000, coordinated across local and CI distribution.

For local and CI APKs signed with the same permanent key, see
[Android release signing](SIGNING.md). The manual `signed_release` option on
`main` builds an unsigned release and signs it in a separate protected job.
Manual runs upload a signed Actions artifact without creating a release. Tag builds
are called by the desktop workflow and join its draft release and shared checksums.
Normal runs remain debug. See [signing and combined release setup](SIGNING.md).

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
2. Start the Android app. A successful transport check briefly shows `Trasporto croc pronto` and hides the warning panel; a persistent green indicator is not expected.
3. In **Invia** (Send), press **File** (Add files) to choose one or
   more small, non-sensitive documents. Press **Cartella** (Add folder)
   to choose one small folder containing nested files and an empty subfolder.
4. Repeat either action to create a multi-root or mixed selection. Check that
   previous roots remain and new files or folders are appended.
5. Review each staged root, its type, aggregate size, and the selection summary.
   Use **Rimuovi** (Remove) on one item or **Svuota** (Clear selection)
   to verify that the selection can be corrected, then prepare the intended
   test selection.
6. Press **Prepara invio** (Prepare and send). The app hashes every private
   staged copy and displays a 32-character code.
   The code is also copied to the Android clipboard.
7. Switch to the messaging application used to communicate the code. Leave
   MoonTransfer in the background while the receiver enters it; the ongoing
   transfer notification must remain visible and identify the current phase.
8. Enter that code in the desktop **Ricevi** tab and start receiving.
9. Check the names, counts, total size and SHA-256 information shown by the
   desktop app, then accept or reject the transfer.
10. If accepted, both applications should report progress and completion. Check
   that files, nested paths, and empty folders appear in the chosen desktop
   destination. A single folder keeps its root name; multiple roots use the
   desktop `MoonTransfer` container. If rejected, Android should report the
   receiver's decision without sending the main payload.
11. Return to MoonTransfer and verify that another selection and transfer can
    be started without closing or restarting the application.

### Receive from desktop on Android

1. Start MoonTransfer on the desktop, open **Invia** (Send), and choose a small,
   non-sensitive file, folder, or mixed selection. Include a nested file and an
   empty folder when testing directory preservation.
2. Start the Android app, open **Ricevi** (Receive), enter the code shown by the
   desktop application, and press **Verifica contenuto** (Receive information).
3. For one file, check its name, size, and SHA-256. For any folder or multi-root
   payload, check the file and folder counts, total size, listed top-level names,
   and the indication that a SHA-256 is included for each file.
4. Press **Rifiuta** (Reject) to notify the desktop sender without downloading
   the payload, or **Accetta** (Accept) to continue.
5. After an accepted payload has been downloaded into private storage and its
   manifest has been verified, Android opens the system save picker.
6. For one file, choose its final name and location. For a folder or multi-root
   payload, choose a destination directory. A single folder is recreated under
   its own root name; multiple roots are recreated inside a dedicated
   `MoonTransfer` child directory. MoonTransfer does not create the destination
   before verification succeeds.
7. Check that both applications report completion and that every saved file,
   nested path, and empty folder is available through the selected Android
   document provider.
8. Verify that the code field and transfer controls are usable again without
   closing or restarting MoonTransfer.

### Lifecycle and recovery checks

Before treating an Android change as manually validated, also exercise these
cases with a small, non-sensitive payload:

1. Start a send, wait for the code, press Home or switch to the messaging app,
   then reopen MoonTransfer. The notification must remain available and the GUI
   must reconnect to the same phase without starting another transfer.
2. While a transfer is active, remove MoonTransfer from the recent-apps screen
   and reopen it. Controls that could start a second operation must remain
   disabled until the existing service finishes or is cancelled.
3. Rotate the device during metadata exchange, payload transfer and the
   receiver decision. Activity recreation must not duplicate `croc`, lose the
   proposal or unlock conflicting controls.
4. Cancel the source picker before choosing a file or folder. Repeat after
   staging at least one root and verify that cancellation preserves the existing
   selection. Separately, cancel the save picker after a verified receive, then
   reopen it with **Scegli destinazione** (Choose where to save). All paths must
   return to usable controls.
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
for up to 15 minutes from verification while the foreground transfer service
remains active. Press **Scegli destinazione** (Choose where to save) to retry, or **Interrompi** (Stop) to discard
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

The system picker returns content URIs rather than normal filesystem paths. For
files, MoonTransfer queries each portable name and optional size, rejects
portable-name collisions, opens every URI through `ContentResolver`, and copies
each document into a separate app-private directory with mode `0600`. For a
folder, `ACTION_OPEN_DOCUMENT_TREE` returns one tree URI; MoonTransfer enumerates
it recursively through `DocumentsContract`, validates document identifiers,
portable paths, collisions, cycles, and the protocol entry limit, rejects
virtual documents, then recreates the snapshot privately with `0700`
directories and `0600` files. These private copies are the controlled sources
used for hashing and by `croc`; their fingerprints and exact tree are checked
again before the main sender starts. Cancellation removes them immediately;
other outcomes can hand them back to the UI for an explicit new send within
the bounded retention window described above. Stale app-owned staging and session
directories are removed on the next start only when no foreground transfer is
active.

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

1. scan the staged roots and calculate a SHA-256 for every regular file;
2. create a protocol-v2 proposal containing a separately generated main-payload
   code;
3. start the main `croc send` process and wait until `croc` has collected and
   hashed all send inputs and announces its code;
4. start a separate metadata sender and expose the single user-facing code only
   after that process is also prepared;
5. transfer the bounded JSON manifest while the main sender remains ready;
6. let the prompted desktop receiver communicate acceptance or rejection
   through the main `croc` connection.

The Android receiver follows the inverse flow:

1. receive the bounded manifest into an isolated app-private directory;
2. validate every protocol field and the bounded file/directory tree;
3. show either the single file's name, size, and SHA-256 or the payload root
   names, file and folder counts, total size, and per-file hash availability
   before download;
4. start the prompted main receiver and write `y` or `n` to `croc` so the
   desktop sender receives a protocol-level acceptance or rejection;
5. for accepted transfers, check private free space and enforce the declared
   byte limit while receiving;
6. verify the exact received tree, size and SHA-256 against the manifest;
7. only after verification, launch Android's `ACTION_CREATE_DOCUMENT` picker
   for one file, or `ACTION_OPEN_DOCUMENT_TREE` for a folder or multiple roots;
   a single folder is recreated with its root name, while multiple roots use a
   dedicated child directory named by the sender (`MoonTransfer` by default);
8. remove the manifest and private payload after completion, rejection,
   cancellation or terminal failure. A recoverable save failure waits for a
   new destination within the 15-minute deadline.

Cancelling the system save picker does not discard the verified private copy;
the user can reopen it within 15 minutes of verification while the service
remains active, or cancel the transfer
to discard it. This ordering avoids touching an existing destination before
integrity checks have passed. For a single file, the system document provider
remains responsible for final name conflicts and overwrite confirmation. For a
tree save, MoonTransfer asks the provider to create the root container,
directories, and files, and attempts to remove that new container if saving is
cancelled or fails.

Both secrets are passed in `CROC_SECRET`, never as command-line arguments.
Every concurrently active process receives a distinct isolated `croc`
configuration directory. Process output is consumed concurrently from stdout
and stderr, bounded per record and redacted before callbacks receive it.
Process completion is determined from the exit status; textual output is
parsed for the send-preparation boundary, progress and rejection-oriented
status. No fixed delay is used to guess when the main sender is ready. A
15-minute inactivity timeout is reset whenever `croc` emits output, so it does
not impose a fixed maximum duration on an active transfer. A separate
15-minute decision timeout automatically rejects an unanswered proposal
instead of leaving the desktop sender waiting indefinitely. Only one send or
receive operation can run at a time.

## Isolation from desktop builds

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
the desktop project. It downloads the explicit source asset attached to that
upstream release, verifies its published SHA-256 digest, and builds against the
included vendored Go modules rather than resolving dependencies during the
build. It then creates a position-independent ARM64 Android executable with cgo
enabled. This lets Go delegate relay hostname resolution to Android's native DNS
resolver, so the app respects the active network, VPN, and Private DNS
configuration. The executable is packaged as `lib/arm64-v8a/libcroc.so`, which
keeps it inside the APK's signed native-library area. The upstream MIT license
is also included in the application package. The Android build command
fingerprints this recipe; when its version, checksum, or build logic changes, it
removes the stale native `croc` cache and rebuilds the distribution instead of
silently reusing an old executable.

## Known limitations

- file, folder, and mixed-selection sending and receiving are implemented on
  Android, up to the protocol limits of 256 top-level roots and 10,000 total
  entries;
- top-level roots and entries in each folder must have distinct portable names;
  virtual SAF documents are rejected because they do not provide the stable
  file-descriptor semantics required for private staging;
- the final SAF copy cannot be made atomically across every third-party document
  provider; MoonTransfer attempts to remove a partial tree container, but
  a provider error or interruption can still leave a partial destination;
- background execution is protected while the app is covered, the user switches
  applications, or its task is removed from the recent-apps screen, but
  force-stopping the app, restarting the device, or a service/process failure
  still ends the transfer;
- Android 15 and later impose a shared six-hour `dataSync` foreground-service
  allowance while the app is in the background; reaching it cancels the active
  transfer, and starting another one may be refused until the allowance resets;
- interrupted transfers cannot yet be resumed from a partial payload;
- debug ARM64 APKs remain the default; signed artifacts and complete draft
  releases require explicit key/environment setup. Non-ARM64 artifacts are not implemented;
- debug signing identities can differ between build hosts, which may require
  uninstalling an existing prototype before installing another test build;
- send readiness and transfer status still depend partly on human-readable
  `croc` output because `croc` does not expose a structured status or progress
  API; MoonTransfer therefore pins the supported `croc` version and tests the
  expected preparation message.

## Local GUI tests

From the checkout root on Linux with the Android environment installed. Software rendering requires neither ADB nor an emulator; it does not replace device testing.

```sh
PYTHONPATH="$PWD/src:$PWD/android/app" \
MOONTRANSFER_KIVY_TOUCH_TESTS=1 KIVY_NO_ARGS=1 KIVY_NO_FILELOG=1 \
SDL_VIDEODRIVER=offscreen LIBGL_ALWAYS_SOFTWARE=1 \
uv run --project android --frozen --group build python -m unittest \
  tests.test_android_header tests.test_android_sharing_ui tests.test_android_scroll -v
```

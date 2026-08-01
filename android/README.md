# MoonTransfer Android experiment

Italian version: [README.it.md](README.it.md)

This directory contains an isolated Kivy and Buildozer environment for the
Android feasibility prototype. It does not replace the PySide6 desktop
application and is not part of desktop release artifacts.

## Current scope

The prototype currently provides:

- a Python 3.13 and Kivy 2.3.1 development environment;
- a Kivy interface for selecting and sending one file;
- generated Android build sources containing only explicitly approved,
  Qt-independent MoonTransfer modules;
- a pinned Buildozer and python-for-android configuration;
- an `arm64-v8a` debug APK target;
- a private recipe that verifies and cross-compiles the pinned `croc` source;
- an Android runtime probe that locates the packaged executable and checks its
  version without exposing a transfer secret;
- file selection through Android's Storage Access Framework (SAF);
- an Android-to-desktop send flow compatible with MoonTransfer protocol v2;
- transfer progress, receiver rejection reporting, cancellation, inactivity
  timeouts and cleanup of private temporary files.

This remains an experimental sender. It cannot receive files, select multiple
files or folders, continue in the background, or build release artifacts for
architectures other than `arm64-v8a`. Only the `INTERNET` permission is
declared; SAF provides access only to the document explicitly chosen by the
user, without broad storage permissions.

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

When the APK starts on Android, it resolves `libcroc.so` from the application's
native library directory and runs `croc --version` in a worker thread. A green
status confirms that the transport executable can be started on the device.

The first invocation can download Python packages, Android tooling and source
archives. Generated source and build output must not be edited or committed.

## Test an Android-to-desktop transfer

This is a manual compatibility test for the experimental sender, not an
end-user release procedure.

1. Build the current desktop application and Android debug APK from the same
   revision.
2. Install the generated `dist/android/moontransfer-<version>-arm64-v8a-debug.apk`
   on an ARM64 Android device.
3. Start MoonTransfer on the desktop, open **Ricevi** (Receive), and choose a
   destination directory.
4. Start the Android app and wait for the green `croc` transport status.
5. Press **Seleziona file** (Select file) and choose a small, non-sensitive
   document from the Android system picker.
6. Check the displayed name and size, then press **Prepara e invia** (Prepare
   and send).
7. The app hashes the private staged copy and displays a 32-character code. The
   code is also copied to the Android clipboard.
8. Enter that code in the desktop **Ricevi** tab and start receiving.
9. Check the filename, size and SHA-256 information shown by the desktop app,
   then accept or reject the transfer.
10. If accepted, both applications should report progress and completion. Check
    that the verified file appears in the chosen desktop destination. If
    rejected, Android should report the receiver's decision without sending the
    main payload.

Closing the Android app or pressing **Interrompi** (Stop) requests termination
of the active `croc` process. The current prototype has no background service,
so it is expected to remain open while sending.

## Android transfer design

The system picker returns a content URI rather than a normal filesystem path.
MoonTransfer queries its portable filename and optional size, opens the URI
through `ContentResolver`, and copies it into a fresh app-private directory with
mode `0600`. The private copy is the controlled source used for hashing and by
`croc`; its fingerprint is checked again before the main sender starts. It is
removed after completion, rejection, failure or cancellation. Stale app-owned
staging and session directories are removed on the next start.

The sender then reuses the desktop protocol instead of sending a raw `croc`
payload:

1. scan the staged file and calculate SHA-256;
2. create a protocol-v2 proposal containing a separately generated main-payload
   code;
3. send the bounded JSON manifest with the single user-facing code;
4. after the desktop receives the manifest, start the main `croc send` process;
5. let the prompted desktop receiver communicate acceptance or rejection
   through the main `croc` connection.

Both secrets are passed in `CROC_SECRET`, never as command-line arguments.
Each session receives an isolated `croc` configuration directory. Process
output is consumed concurrently from stdout and stderr, bounded per record and
redacted before callbacks receive it. Process completion is determined from the
exit status; textual output is parsed only for progress and rejection-oriented
status. A 15-minute inactivity timeout is reset whenever `croc` emits output,
so it does not impose a fixed maximum duration on an active transfer.

## Isolation from desktop releases

Android dependencies live in this directory's own `pyproject.toml` and
`uv.lock`. The root project keeps PySide6 as its only GUI runtime. Buildozer
receives a generated source tree, while `MoonTransfer.spec` continues to package
`src/moontransfer/app.py` for desktop systems.

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
the application package.

## Known limitations

- only single-file Android-to-desktop sending is implemented;
- directory and multiple-file selection are not implemented;
- Android receiving and destination conflict handling are not implemented;
- no foreground service keeps a transfer alive after the app is closed;
- only a debug `arm64-v8a` APK is produced;
- transfer status still depends partly on human-readable `croc` output because
  `croc` does not expose a structured progress API.

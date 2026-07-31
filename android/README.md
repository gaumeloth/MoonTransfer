# MoonTransfer Android experiment

Italian version: [README.it.md](README.it.md)

This directory contains an isolated Kivy and Buildozer environment for the
Android feasibility prototype. It does not replace the PySide6 desktop
application and is not part of desktop release artifacts.

## Current scope

The scaffold currently provides:

- a Python 3.13 and Kivy 2.3.1 development environment;
- a minimal Kivy entry point that imports the shared MoonTransfer protocol;
- generated Android build sources containing only explicitly approved,
  Qt-independent MoonTransfer modules;
- a pinned Buildozer and python-for-android configuration;
- an `arm64-v8a` debug APK target;
- a private recipe directory for the future Android `croc` integration.

It does not yet provide file selection, transfers, Android services or a
packaged `croc` executable. Only the `INTERNET` permission is declared. File
access will use Android's Storage Access Framework instead of broad storage
permissions.

## Host prerequisites

Android builds require Linux or macOS. The current configuration expects Java
17, the standard native build tools and Rust. Buildozer downloads the configured
Android SDK and NDK when necessary.

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
  pkgconf cmake libffi openssl automake gettext make gcc
```

Install Rust with the method documented at <https://rustup.rs/> and make sure
`cargo` and `rustc` are available on `PATH`.

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

`doctor` checks host-side prerequisites. `prepare` recreates the generated
source tree under `build/android/source`. `run` launches the Kivy scaffold on
the desktop for a quick UI smoke test. `build` produces a debug APK under
`dist/android`.

The first invocation can download Python packages, Android tooling and source
archives. Generated source and build output must not be edited or committed.

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

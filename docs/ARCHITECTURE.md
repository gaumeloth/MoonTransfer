# Architecture and ownership

[Italiano](ARCHITECTURE.it.md) | [MoonTransfer](../README.md)

## Contents

- [Platform boundaries](#platform-boundaries)
- [Where to change things](#where-to-change-things)
- [Architecture notes](#architecture-notes)
- [Experimental Android target](#experimental-android-target)

## Platform boundaries

- **Shared, without Qt:** `src/moontransfer/codes.py` extracts and normalizes codes; `protocol.py`, `payload.py`, `files.py`, `croc.py`, `progress.py`, `messages.py`, `build_info.py` and `cancellation.py` define reused contracts.
- **Desktop:** `app.py`, `widgets.py`, `transfer.py`, `runner.py`, `tasks.py` and `desktop.py` own Qt UI, controllers, processes and desktop integration; they are not the Android runtime.
- **Android:** under `android/app/moontransfer_android/`, `application.py` coordinates the UI; `moontransfer.kv`, `widgets.py` and `theme.py` define presentation; `sender.py`, `receiver.py` and the service own sessions using `subprocess.Popen`. `sharing.py`, `documents.py` and `storage.py` handle intents, URIs and saving. `app_state.py` and `ui_state.py` separate state and presentation.
- **Native integration:** Java sources under `android/` and `android_runtime.py`, `service_client.py`, `service_protocol.py`, `service.py`, `transfer_service.py` connect the activity, foreground service and notification.
- **Distribution:** `tools/android_signing.py` isolates signing and verification; `android/release.toml` coordinates versionCode; `tools/release_assets.py` validates the release package set. The [release guide](RELEASING.md) describes both workflows.

This is an ownership map, not an exhaustive file inventory.


## Where to change things

Use the existing module boundaries when choosing where to make a change:

- `src/moontransfer/app.py`: application entry point, main window, send tab,
  receive tab, input validation, user dialogs, and binding controller events to
  the GUI.
- `src/moontransfer/assets/`: version-controlled visual assets shared by the
  project documentation and the application. `branding/` contains the main
  logo; `icons/` contains the source PNG packaged as the application icon.
- `src/moontransfer/resources.py`: stable paths to packaged visual assets for
  both source runs and PyInstaller bundles.
- `src/moontransfer/build_info.py`: validated runtime build identity and safe,
  copyable diagnostics shared by desktop and Android.
- `src/moontransfer/transfer.py`: explicit transfer states, send and receive
  controllers, session lifecycle, process and timeout coordination, metadata
  flow, background payload operations, receive limits, final verification, and
  cleanup.
- `src/moontransfer/tasks.py`: cancellable `QThread` worker used for file
  inventory, destination comparison, final verification, and cross-device
  copies without blocking the GUI event loop.
- `src/moontransfer/cancellation.py`: Qt-independent cancellation exception
  shared by background workers and file operations.
- `src/moontransfer/widgets.py`: reusable Qt widgets such as the status label,
  technical output panel, terminal-like output view, and transfer progress
  widget.
- `src/moontransfer/croc.py`: `croc` executable discovery, command arguments,
  transfer-code environment variables, isolated `croc` configuration, and safe
  command previews for logs.
- `src/moontransfer/protocol.py`: MoonTransfer control metadata format, protocol
  versions, generated codes, bounded payload manifest, portable path
  validation, SHA-256 validation, and metadata JSON read/write rules.
- `src/moontransfer/payload.py`: source-tree inventory, mutation detection,
  destination comparison, exact received-tree verification, and safe
  publication of single-root or multi-root payloads.
- `src/moontransfer/files.py`: temporary session directories, destination
  primitives, stable file fingerprints, cancellable SHA-256 hashing, unique
  file and directory names, and cross-filesystem movement.
- `src/moontransfer/progress.py`: parsing `croc` progress output, aggregating
  per-file samples, and formatting file sizes, transfer rates, elapsed time,
  and remaining time.
- `src/moontransfer/messages.py`: user-facing status messages derived from
  process output and process results.
- `src/moontransfer/runner.py`: `QProcess` lifecycle, stdout/stderr splitting,
  process termination, and stdin replies to `croc` prompts.
- `src/moontransfer/desktop.py`: opening folders through the platform file
  manager and cleaning the environment used for external desktop commands.
- `tools/build.py`: common PyInstaller build orchestration.
- `tools/build_metadata.py`: build version and commit resolution plus
  deterministic generation of the metadata embedded in packaged applications.
- `tools/fetch_croc.py`: pinned `croc` release selection, download, checksum
  verification, archive extraction, and bundled binary installation.
- `tools/check_latest_croc.py`: compatibility checks against the latest upstream
  `croc` release.
- `tools/package_release.py`: host/target validation, bundled-`croc` version
  check, and creation of versioned release archives with license and
  documentation files.
- `tools/prepare_android.py`: deterministic Android source generation and
  embedded build identity.
- `tools/android.py`: Android host diagnostics, source preparation, Buildozer
  orchestration, APK validation, and versioned artifact staging.
- `scripts/build.sh` and `scripts/build.ps1`: user-facing build wrappers and
  prerequisite checks.
- `scripts/android.sh`: frozen, repository-root-independent wrapper for the
  isolated Android environment.
- `MoonTransfer.spec`: PyInstaller `onedir` packaging configuration, including
  the native macOS application bundle.
- `.github/workflows/android-build.yml`: Android tests, toolchain diagnostics,
  validated ARM64 debug APK builds, and CI artifact uploads.
- `.github/workflows/release-builds.yml`: native test, build, artifact, checksum,
  and draft pre-release automation.
- `.github/dependabot.yml`: monthly pull requests for pinned GitHub Action
  updates.

When changing a runtime module, update or add the matching test file under
`tests/` whenever practical. The test names already mirror most runtime and
maintenance modules.

## Architecture notes

- Desktop MoonTransfer starts `croc` with `QProcess`, without going through shells such
  as bash, fish, or PowerShell.
- `src/moontransfer/app.py` keeps the application entry point, main window, and
  send/receive tabs. It owns widget layout, local input validation, user
  dialogs, and presentation of controller events. `transfer.py` owns the
  explicit state machines and the orchestration of metadata and main-payload
  processes, timeouts, session resources, verification, and cleanup. Other
  reusable behavior is split into `croc.py` for `croc` command construction,
  `protocol.py` for bounded control manifests, `payload.py` for inventory and
  exact tree verification, `files.py` for low-level filesystem primitives,
  `progress.py` for transfer output parsing and aggregation, `messages.py` for
  user-facing status text, `desktop.py` for file manager integration,
  `runner.py` for `QProcess` handling, `tasks.py` for cancellable background
  operations, `cancellation.py` for the shared cancellation contract, and
  `widgets.py` for shared Qt widgets.
- The bundled `croc` version is pinned in `pyproject.toml`; supported release
  archives are verified with versioned SHA-256 hashes before extraction.
- When sending, MoonTransfer generates metadata and main payload codes itself.
  Protocol v2 describes one or more roots with a bounded flat manifest of files
  and directories. Each file entry includes its exact size and SHA-256 hash.
  A v2 receiver can also normalize a legacy v1 single-file proposal. The
  visible code is only the metadata code. Transfer codes are passed through
  `CROC_SECRET`, because modern non-classic `croc` does not accept custom send
  codes through `--code` on Unix systems:

```text
CROC_SECRET=<hidden> croc --classic=false --ignore-stdin --disable-clipboard send --no-local <path> [<path> ...]
```

`--no-local` avoids `croc`'s local relay, which can make negotiation unstable
in tests with two instances on the same machine.
`--classic=false` keeps MoonTransfer on `croc`'s modern transfer mode even if
the user's global `croc` configuration has remembered classic mode.

Before exposing the metadata code, the sender verifies that the inventoried
roots have not changed and starts one main `croc send` process with every
selected root. MoonTransfer waits until the pinned `croc` version announces
its code: this happens after `croc` has collected and hashed the send inputs,
and is therefore used as the preparation boundary. It then starts the metadata
sender in a second, isolated `croc` configuration directory and publishes the
metadata code only after that process reaches the same boundary. The two
processes overlap only while the small manifest is transferred; afterwards the
prepared main sender remains waiting for the receiver's decision.

The receiver starts the main `croc` process without `--yes`, then MoonTransfer
writes `y` or `n` to that process based on the user's GUI choice. This uses
`croc`'s own accept/reject prompt instead of a separate MoonTransfer decision
transfer. If the receiver rejects the payload, the main transfer is refused
and no payload content is downloaded. A main sender that exits before the
metadata exchange completes is treated as a transfer failure rather than
publishing a code for an unusable session.

- When receiving metadata, control files are received into temporary session
  directories first. Transfer codes are passed through `CROC_SECRET`, not as
  positional command-line arguments:

```text
CROC_SECRET=<hidden> croc --classic=false --ignore-stdin --yes --overwrite
```

The main payload receive process intentionally keeps stdin open and does not use
`--yes`, so MoonTransfer can answer `croc`'s prompt:

```text
CROC_SECRET=<hidden> croc --classic=false --overwrite
```

Each transfer session also gives `croc` an isolated temporary configuration
directory, so MoonTransfer does not depend on or modify the user's global
`croc` settings.

The command preview shown in the technical details masks internal transfer
codes. The main payload is received into a fresh staging directory. MoonTransfer
rejects unlisted paths, missing entries, type changes, links, special files,
size mismatches, and SHA-256 mismatches before publishing the verified result.
Multiple selected roots are published inside one container directory so a
group is not intentionally merged into existing destination content.

- On desktop, potentially long local operations run in a cancellable background `QThread`:
  sender inventory and fingerprinting, comparison with existing destination
  content, final received-tree verification, and cross-device copies. The
  sender records every source file identity together with its hash, rescans the
  selected roots, and checks the fingerprints before starting the main `croc`
  process. Final receiver verification remains authoritative because `croc`
  opens source paths after MoonTransfer's last local check.
- Build reproducibility depends on `uv.lock`, the pinned `croc` version, and
  the versioned SHA-256 hashes in `pyproject.toml`.

## Experimental Android target

Android feasibility work is isolated under `android/` and does not replace the
PySide6 desktop application. It uses a separate Python 3.13 environment, Kivy,
Buildozer, and its own `uv.lock`. The Android source tree is generated from an
explicit allowlist of Qt-independent MoonTransfer modules, so the protocol is
shared without adding Kivy to desktop runtime dependencies.

The current prototype packages a verified ARM64 `croc` executable and can send
or receive files, folders, and mixed selections between Android and the desktop
application using the shared protocol-v2 manifest and Android's Storage Access
Framework. A `dataSync` foreground service owns active transfers, so switching
applications does not abort `croc`; a private state-aware notification reports
phase and available progress metrics and provides a session-bound stop action,
then leaves a dismissible result. The service handles Android 15 `dataSync`
timeouts and invalid sticky restarts, but interrupted sessions still cannot be
resumed. Signed Android APKs are now included in tag-driven draft releases,
after the signing environment has been configured.
The dedicated Android CI workflow nevertheless creates a structurally validated
ARM64 debug APK for testing; it is deliberately kept separate from published
GitHub Releases.

An opt-in manual run on `main` can also build a release APK and sign it in a
separate protected job, using the same key as local release builds. Tag builds
join the desktop packages in one draft release. This requires explicit key setup
and a coordinated versionCode; see [Android signing](../android/SIGNING.md).

Setup, diagnostics, build commands, design details, and manual compatibility
tests are documented in [android/README.md](../android/README.md).

# MoonTransfer

<p align="center">
  <img
    src="src/moontransfer/assets/branding/moontransfer-logo.png"
    alt="MoonTransfer logo"
    width="640"
  >
</p>

Italian version: [README.it.md](README.it.md)

MoonTransfer is a GUI for sending and receiving files and folders through
[`croc`](https://github.com/schollz/croc).

Its goal is to make file transfer simple: the sender chooses one or more files
and folders, MoonTransfer shows a code, and the receiver enters that code to
save the selected content.

MoonTransfer does not implement its own cryptographic protocol. Security,
connection handling, and transfer are provided by `croc`; MoonTransfer only
provides the graphical interface and includes the `croc` binary in the built
application.

## Contents

- [Start here](#start-here)
- [Current status](#current-status)
- [Transport compatibility](#transport-compatibility)
- [Quick guide](#quick-guide)
- [Download a pre-built alpha](#download-a-pre-built-alpha)
- [Use MoonTransfer](#use-moontransfer)
- [Development and documentation](#development-and-documentation)
- [Licenses](#licenses)

## Start here

| Goal | Guide |
| --- | --- |
| Use the desktop app | [Download an alpha](#download-a-pre-built-alpha) and [usage](#use-moontransfer) |
| Use or test Android | [Android installation and guide](android/README.md#installation-and-first-start) |
| Build or contribute | [Desktop build](docs/BUILD.md), [Android build](android/README.md#host-prerequisites), [contributing](CONTRIBUTING.md) |
| Resolve a problem | [Troubleshooting](docs/TROUBLESHOOTING.md) |

### Distribution channels

- **Published releases:** use assets on the Releases page. The current `alpha.4` release contains four desktop archives and a signed ARM64 APK; features described here refer to current source and may be newer.
- **Actions artifacts:** test builds with an identifiable version and commit. Android normally produces a debug APK; dedicated manual runs can produce APKs signed with the project key without publishing releases.
- **New pre-release tags:** the workflow prepares a draft containing four desktop archives and one signed ARM64 APK. Publication remains manual; signing setup is a prerequisite.

See [artifacts and releases](docs/RELEASING.md) to select the appropriate workflow. Desktop uses Qt/PySide6; Android uses Kivy and native system integration.

## Current status

MoonTransfer is in an early stage. The main flow is already working:

- sending one or more files, folders, or a mixed selection;
- preserving nested and empty folders;
- receiving a bounded manifest through a code before accepting the main
  download;
- using `croc`'s native accept/reject prompt for the main transfer;
- showing `croc` output in the GUI;
- generating one user-facing code while keeping internal control codes hidden;
- showing selected roots, total size, and per-file SHA-256 information before
  downloading the main content;
- receiving into isolated staging, checking the exact manifest, and publishing
  the result only after verification;
- local build with PyInstaller;
- automatic download of the `croc` binary during the build;
- pinned `croc` version and SHA-256 verification for supported platforms;
- final bundle with `croc` included;
- an embedded build identity containing the full MoonTransfer version, source
  commit, bundled `croc` version, and MoonTransfer protocol version;
- automated testable `onedir` artifacts for Linux x86_64, Windows x86_64,
  macOS Intel, and macOS Apple Silicon.

The current public alpha, `v0.1.0-alpha.4`, is distributed from the
[GitHub Releases page](https://github.com/gaumeloth/MoonTransfer/releases) as
pre-built `onedir` archives and a signed ARM64 Android APK. The desktop builds
are not signed or notarized and all artifacts are intended for early testing
rather than production use. Native installers are not available yet.

On Linux and Windows, the archive contains a portable `MoonTransfer` folder:
keep the entire folder, not just its executable. On macOS, it contains a
`MoonTransfer.app` application bundle, which must likewise be kept intact.

On desktop, the window title shows the full build version. The information button in the
lower-right corner opens a copyable diagnostic summary containing the version,
commit, bundled `croc`, protocol, Python runtime, and platform. It deliberately
does not include transfer codes or local paths. Include this summary when
reporting a build-specific problem.

## Transport compatibility

> [!IMPORTANT]
> Builds produced from the current source bundle `croc 11.0.1`. They cannot
> transfer data to or from MoonTransfer builds based on `croc 10.x`. Update
> MoonTransfer on both devices before starting a transfer; using the same
> MoonTransfer release on both sides is the safest choice.

The compatibility boundary is:

| MoonTransfer build | Bundled `croc` | Compatible with the current source |
| --- | --- | --- |
| `v0.1.0-alpha.1` | `10.4.13` | No |
| `v0.1.0-alpha.2` | `10.7.0` | No |
| `v0.1.0-alpha.3`, `v0.1.0-alpha.4` and current source | `11.0.1` | Yes |

The `alpha.1` and `alpha.2` archives remain useful only with other pre-`croc
11` builds. Use `alpha.4` or a newer build at both endpoints. This is a
transport-protocol incompatibility, not an operating-system incompatibility:
current desktop and Android builds remain compatible when they use `croc 11`
and the same MoonTransfer protocol version.

`croc 11` introduced version 2 of its PAKE wire protocol and deliberately
rejects peers using the earlier handshake. The new handshake explicitly binds
the key exchange to the two peers, their roles, the session, room and
transcript; it also strengthens key derivation and salt handling and adds
mutual key confirmation. Falling back silently would remove those protections,
so MoonTransfer does not attempt it. See the official [`croc 11.0.0` release
notes](https://github.com/schollz/croc/releases/tag/v11.0.0) and the upstream
[security upgrade](https://github.com/schollz/croc/pull/1212).

With a mixed old/new pair, the connection fails while securing the channel,
before MoonTransfer can exchange its metadata manifest or start the main
payload. No selected payload is downloaded or published. Depending on which
side reports the error, the technical details can mention an unsupported PAKE
protocol version and ask to upgrade both clients, or show the more general
`could not secure channel` message.

## Quick guide

To use the pre-built alpha, follow these steps in order:

1. open the [Releases page](https://github.com/gaumeloth/MoonTransfer/releases);
2. open the most recent alpha release;
3. download the archive matching your operating system and architecture;
4. extract the complete archive;
5. open the extracted folder and start MoonTransfer.

You do not need to install Python, `uv`, or `croc` when using a pre-built
archive.

## Download a pre-built alpha

Release files use names such as:

```text
MoonTransfer-0.1.0-alpha.4-linux-x86_64.tar.gz
MoonTransfer-0.1.0-alpha.4-windows-x86_64.zip
MoonTransfer-0.1.0-alpha.4-macos-x86_64.tar.gz
MoonTransfer-0.1.0-alpha.4-macos-arm64.tar.gz
```

The version number may be newer than the example. Download only files attached
to the official [MoonTransfer Releases
page](https://github.com/gaumeloth/MoonTransfer/releases).

Expand only the operating system you are using.

<details>
<summary>Linux</summary>

The published Linux archive currently supports x86_64 Intel/AMD systems. You
can check your architecture with:

```sh
uname -m
```

If the output is `x86_64`, download the file ending in
`linux-x86_64.tar.gz`. Extract it, open the resulting versioned folder, and
start the `MoonTransfer` file.

From a terminal inside the extracted folder, you can instead run:

```sh
./MoonTransfer
```

Linux ARM64 is supported by the build tools but is not currently published as
an automated release artifact. Build from source on that architecture.

</details>

<details>
<summary>Windows</summary>

The published Windows archive currently supports x86_64 Intel/AMD systems,
which includes most Windows 10 and Windows 11 computers.

1. Download the file ending in `windows-x86_64.zip`.
2. Right-click the ZIP file and choose **Extract All**.
3. Open the extracted versioned folder.
4. Double-click `MoonTransfer.exe`.

Do not run the executable directly from inside the ZIP and do not move it away
from the `_internal` folder.

The alpha is not code-signed, so Microsoft Defender SmartScreen may show an
unknown-publisher warning. Confirm that the archive came from the official
Releases page and verify its checksum before choosing **More info > Run
anyway**.

</details>

<details>
<summary>macOS</summary>

Download the archive matching the Mac processor:

- `macos-arm64.tar.gz` for Apple Silicon Macs with an M-series processor;
- `macos-x86_64.tar.gz` for Intel Macs.

Double-click the downloaded archive to extract it, open the resulting versioned
folder, and start `MoonTransfer.app`.

The alpha is not signed or notarized. On first start, Control-click
`MoonTransfer.app`, choose **Open**, and confirm. Depending on the macOS
version, it can also be allowed from **System Settings > Privacy & Security**.

</details>

Each alpha release also contains `SHA256SUMS`. It lists the expected SHA-256
digest of every downloadable archive and can be used to check that a download
is complete and unchanged.

## Use MoonTransfer

To complete a transfer, you need two people or two computers:

- the sender opens the **Invia** (Send) tab and generates a code;
- the receiver opens the **Ricevi** (Receive) tab and enters that code.

Both computers must be connected to the Internet. The code must be shared
outside MoonTransfer, for example via chat, phone, or email.

### Send files and folders

On the sending computer:

1. open MoonTransfer;
2. go to the **Invia** (Send) tab;
3. drag files and folders into the selection list, or use **Aggiungi file**
   (Add files) and **Aggiungi cartella** (Add folder);
4. review the list and use **Rimuovi** (Remove) or **Svuota** (Clear) if needed;
5. press **Invia** (Send);
6. wait while MoonTransfer scans the selection and calculates SHA-256 hashes;
7. share the displayed code with the receiver.

The code first lets the receiver download a bounded manifest containing the
selected paths, sizes, and per-file SHA-256 hashes. Before showing that code,
MoonTransfer has already prepared one main `croc` sender for the complete
payload. It waits for acceptance or rejection through `croc`'s native prompt;
preparation does not send the main payload before acceptance.

During the main transfer, MoonTransfer shows overall progress, transferred size,
current speed, elapsed time, and estimated remaining time when `croc` provides
enough progress information.

MoonTransfer scans and fingerprints regular files in the background before
showing the code. It checks the selected tree again before starting the main
process. The **Stop** button can cancel preparation, verification, or an active
transfer.

The code is one-time use: it is valid for that transfer and should not be
reused.

### Receive files and folders

On the receiving computer:

1. open MoonTransfer;
2. go to the **Ricevi** (Receive) tab;
3. paste the received code;
4. choose the destination folder;
5. press **Ricevi** (Receive);
6. review the selected roots, file and folder counts, total size, and SHA-256
   information shown by MoonTransfer;
7. expand the manifest details if you need the path, size, and hash of each
   file;
8. accept or reject the transfer;
9. if a single file with the same name already exists, choose whether to skip,
   overwrite, or save the incoming file with another name;
10. if a folder or group conflicts with existing content, reject it or use the
    proposed unique folder name;
11. wait for the transfer to complete.

The main payload is downloaded only after MoonTransfer accepts `croc`'s main
transfer prompt. If you reject the transfer, MoonTransfer connects only to
refuse the main transfer and does not download its content. At the end,
MoonTransfer verifies the exact set of paths, entry types, sizes, and per-file
SHA-256 hashes before publishing anything in the final destination.

Destination comparison and final SHA-256 verification run in the background.
The **Stop** button remains available while these checks are in progress.

During the main transfer, MoonTransfer shows overall progress, downloaded size,
current speed, elapsed time, and estimated remaining time when `croc` provides
enough progress information.

A single received file or folder keeps its original root name. A selection
with multiple roots is stored in a container folder (`MoonTransfer` by default,
or the portable name chosen by the sender). Existing
folders are never merged or recursively overwritten; MoonTransfer proposes a
unique name such as `MoonTransfer (1)` instead.

### Codes, results and recovery

On desktop and Android, paste the code or the complete MoonTransfer message
into **Ricevi**. The shared parser extracts one distinct 32-hexadecimal code,
including its spaced display format. Ambiguous text containing different codes
is not accepted automatically. Importing a code never starts a transfer.

Desktop remembers the last destination and shows the actual saved path after
verification. Android reopens the system picker at the last destination when
the provider supports it; saving still requires confirmation. The Android
result offers **Apri** for saved content and **Condividi** for a single file.
Opening a folder requires a compatible document handler. The proposal's
**Dettagli** view lists paths, sizes and file hashes in bounded pages.

If final saving fails, the verified copy can be saved to another destination
without downloading again. Desktop retains it for up to 15 minutes after the
first save failure; Android allows 15 minutes from verification to choose or
retry a destination. Stop, timeout or termination of the owning process ends
this opportunity. Android document providers may leave partial output after
a failed write; inspect the previous destination before retrying.

**Prepara nuovo invio** starts a new transfer with new codes, not a partial
resume. Desktop rescans the selected originals. Android can reuse the prepared
copies for up to 15 minutes after the result is displayed, until app closure;
changes to originals require selecting them again. Explicit cancellation
discards the prepared Android copies. Copies left by a killed process are
cleaned on the next startup, not offered as resumable transfers.

The optional `container_name` manifest field does not change protocol 2 or
transport compatibility. Older receivers ignore it and use `MoonTransfer` for
multiple roots. A single file or folder always keeps its original name.

### Current payload limits

MoonTransfer currently accepts regular files and ordinary folders, including
empty folders. Symbolic links, junction-like entries, sockets, FIFOs, devices,
and other special filesystem objects are rejected rather than followed or
recreated.

A payload can contain at most 10,000 manifest entries and 256 selected roots.
The manifest is limited to 4 MiB. A folder and one of its descendants cannot be
selected as separate roots, and root names that would collide on a
case-insensitive or Unicode-normalizing filesystem are rejected.

If the transfer does not start, check that both computers are connected to the
Internet and that any firewall or corporate network is not blocking the
connections used by `croc`.

## Development and documentation

- [Desktop build and running from source](docs/BUILD.md)
- [Contributing, testing and maintaining documentation](CONTRIBUTING.md)
- [Architecture and module ownership](docs/ARCHITECTURE.md)
- [Workflows, test artifacts and releases](docs/RELEASING.md)
- [Troubleshooting and download verification](docs/TROUBLESHOOTING.md)
- [Android guide](android/README.md) and [APK signing](android/SIGNING.md)

## Licenses

MoonTransfer is distributed under the GNU General Public License version 3.
See the full license text in [LICENSE](LICENSE).

Third-party components keep their own licenses. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for third-party components,
in particular `croc`, PySide6/Qt for Python, Kivy, Buildozer, and
python-for-android.

# Troubleshooting

[Italiano](TROUBLESHOOTING.it.md) | [MoonTransfer](../README.md)

## Contents

- [Qt SVG icon warnings on Linux](#qt-svg-icon-warnings-on-linux)
- [Verify downloads](#verify-downloads)
- [Android installation and updates](#android-installation-and-updates)
- [Transport unavailable or transfer interrupted](#transport-unavailable-or-transfer-interrupted)
- [Received content and storage](#received-content-and-storage)
- [Safe bug reports](#safe-bug-reports)

## Qt SVG icon warnings on Linux

When MoonTransfer is started from a terminal, Qt may print warnings such as:

```text
qt.svg: Cannot read file '/usr/share/icons/BeautyLine/places/16/folder-new.svg',
because: Start tag expected. (line 1)
```

This means Qt tried to load an SVG icon from the current system icon theme, but
that icon file is not valid SVG. It usually points to a corrupted, empty,
truncated, or otherwise invalid icon file in the desktop theme. It does not
affect file transfers, `croc`, encryption, or the received file content. At
most, a file-dialog or folder icon may be missing or displayed incorrectly.

To check the icon file on the affected system:

```sh
file /usr/share/icons/BeautyLine/places/16/folder-new.svg
head -n 5 /usr/share/icons/BeautyLine/places/16/folder-new.svg
```

On Arch-based systems such as Garuda, you can also check which package owns the
file:

```sh
pacman -Qo /usr/share/icons/BeautyLine/places/16/folder-new.svg
```

The proper fix is to reinstall or update the icon theme package, choose another
icon theme, or repair the invalid SVG file.

## Verify downloads

Download packages and `SHA256SUMS` from the same official release or Actions run.
From the directory containing the downloaded files, compute the SHA-256 digest
of each package you intend to use and compare it with its exact filename in
`SHA256SUMS`. Replace `PACKAGE` with the actual filename.

```sh
# Linux
sha256sum "PACKAGE"
# macOS
shasum -a 256 "PACKAGE"
```

```powershell
# Windows
Get-FileHash -Algorithm SHA256 -LiteralPath "PACKAGE"
```

When all files listed in `SHA256SUMS` are present, Linux can check the complete
set with `sha256sum -c SHA256SUMS`; macOS with `shasum -a 256 -c SHA256SUMS`.
Missing files must not be mistaken for corrupted downloads.
A matching checksum detects changed bytes; it does not establish trust if both
the file and checksum came from an untrusted source.

With Android SDK Build Tools on PATH, verify a signed APK and print its public
certificate with `apksigner verify --verbose --print-certs "PACKAGE.apk"`.
Compare the certificate SHA-256 with the project's trusted signing fingerprint,
not the APK file checksum: these identify different things.
See the official [apksigner reference](https://developer.android.com/tools/apksigner)
and [project signing guide](../android/SIGNING.md).

## Android installation and updates

- Use the ARM64 APK on a compatible device (declared minimum Android 7.0/API 24).
  x86_64 emulators with ARM translation are not validated native targets.
- Never install the intermediate unsigned APK. A debug APK and a project-key
  APK cannot normally update each other; local and CI debug keys may also differ.
- Before uninstalling to change signing identity, save needed content outside
  private app storage: uninstalling deletes private data. Do not clear app data
  as a routine first troubleshooting step.
- An update needs the same application ID, compatible signature and appropriate
  versionCode. Build version text alone does not determine update eligibility.

## Transport unavailable or transfer interrupted

Open the information dialog on both endpoints and compare build, protocol and
bundled croc. Read [transport compatibility](../README.md#transport-compatibility)
before interpreting a failure as a network problem.
If croc exits during `--version`, it is failing before any transfer; record
the exit code and device architecture. An ARM translation crash is not evidence
that the same APK is broken on a physical ARM64 device.

If version checks pass, record the failed phase and try a small non-sensitive
file with both apps in the foreground. Check network changes, VPN/firewall
restrictions and Android notification permissions. Do not disable device security
or SELinux to work around a crash. Interrupted transfers do not resume their
network session: start a new transfer and communicate its new code.

## Received content and storage

Transfer completion and final publication are separate steps on Android.
After verification, use the system picker to save; if dismissed, use
**Scegli destinazione** while the verified result remains available.
Check the actual provider/directory selected, not only the default Downloads view.
Cloud providers can require their own connection and permissions.

**Apri** and **Condividi** depend on URI access and compatible installed apps;
opening a folder is not supported uniformly by providers. A failed open action
does not by itself mean saving failed: check the destination independently.
Allow space for private staging and the final copy; the required free space can
exceed the payload size. See [Android results and recovery](../android/README.md#results-and-recovery).

## Safe bug reports

Include both endpoints' diagnostic summaries, the failed phase, steps and
redacted errors. Exclude transfer codes, private paths, keystores and passwords.
File verification checks integrity against the manifest, not whether the content
is safe to open. Accept only expected transfers and share codes privately.
See [contributor reporting guidance](../CONTRIBUTING.md#bug-reports-and-technical-logs).

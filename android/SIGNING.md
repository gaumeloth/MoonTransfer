# Android release signing

[Italiano](SIGNING.it.md)

Debug builds are unchanged. Release builds use the **same permanent private key**
locally and in GitHub Actions. A release build is compiled unsigned, then checked,
aligned and signed separately; the build toolchain never receives signing secrets.
Pre-release tags now request a signed APK alongside desktop builds; a single
publisher attaches all five packages to one **draft** GitHub Release. No permanent
key is generated automatically, and nothing is published without manual approval.

## Contents

- [One-time setup](#one-time-setup)
- [Local signed build](#local-signed-build)
- [CI signed build](#ci-signed-build)
- [Desktop and Android together](#desktop-and-android-together)
- [Installation transition](#installation-transition)
- [Test without the permanent key](#test-without-the-permanent-key)
- [Verify GitHub setup](#verify-github-setup)

## One-time setup

Use Java 17 and Python 3.11+ (the Android environment also works). From the project root:

```sh
python3 -m tools.android_signing init --keystore "$HOME/.config/moontransfer/signing/release.p12"
```

Run this yourself in an interactive terminal. Password prompts do not echo.
The command creates a PKCS12 keystore (RSA 4096, validity 10000 days, alias
`moontransfer`) with file mode 0600, refuses existing paths and prints only the
public certificate fingerprint. The key password is the keystore password.
Back up the keystore and save the password separately in a password manager;
losing the key prevents ordinary updates of directly distributed APKs. Never
commit the key, encode it into documentation, attach it to a release, or send
its password in chat. Base64 encoding is not encryption.

On GitHub, create **Settings > Environments > android-signing**. Before adding
secrets, select **Selected branches and tags** and allow the `main` branch plus
tag rules `v*-alpha.*`, `v*-beta.*`, `v*-rc.*`, never pull-request refs. The workflow
also checks the strict tag syntax and that its commit belongs to `main`.
Require a reviewer where available. Keep `main`
protected through PRs; signing workflow edits are security-sensitive.

Add these **environment secrets**, not repository-wide secrets:

| Name | Value |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Base64 encoding of the same local `release.p12` |
| `ANDROID_STORE_PASSWORD` | Keystore password |
| `ANDROID_KEY_PASSWORD` | Key password (same for a key created above) |

Add these **environment variables**:

| Name | Value |
| --- | --- |
| `ANDROID_KEY_ALIAS` | `moontransfer` |
| `ANDROID_CERTIFICATE_SHA256` | Public SHA-256 fingerprint printed during initialization |

Upload without displaying the keystore or passwords (requires authenticated `gh`):

```sh
base64 < "$HOME/.config/moontransfer/signing/release.p12" | gh secret set ANDROID_KEYSTORE_BASE64 --env android-signing --repo gaumeloth/MoonTransfer
gh secret set ANDROID_STORE_PASSWORD --env android-signing --repo gaumeloth/MoonTransfer
gh secret set ANDROID_KEY_PASSWORD --env android-signing --repo gaumeloth/MoonTransfer
```

The password commands prompt interactively. Set the two public variables in the
GitHub UI. Creating the environment alone does not configure its protection rules.

## Local signed build

Select a version whose numeric base matches `pyproject.toml`, and record a
`versionCode` greater than **every previously distributed local or CI release**.
`android/release.toml` records this number (initially 2; debug builds use 1).
Before each new release, increase it through a PR; tags always use that committed
value. The CLI validates the range 2..2100000000, but does not maintain a global
counter: the maintainer must coordinate it with any manual overrides. Use the
same code for local/CI builds of the same release; use a new code for a new update.

```sh
version=0.1.0-dev.signed.1
version_code=$(python3 -m tools.android release-version-code)
commit=$(git rev-parse HEAD)
./scripts/android.sh build --release-unsigned --version-code "$version_code" --version "$version" --commit "$commit"
./scripts/android.sh package --release-unsigned --version "$version" --commit "$commit"
python3 -m tools.android_signing sign \
  --apk "release/MoonTransfer-${version}-android-arm64-release-unsigned.apk" \
  --output "release/MoonTransfer-${version}-android-arm64.apk" \
  --keystore "$HOME/.config/moontransfer/signing/release.p12" \
  --expected-sha256 YOUR_PUBLIC_CERTIFICATE_SHA256 \
  --version "$version" --commit "$commit" --version-code "$version_code"
```

Replace the fingerprint placeholder. Signing prompts for passwords; an empty
key-password answer reuses the store password. Noninteractive signing instead
requires `MOONTRANSFER_ANDROID_STORE_PASSWORD` and `MOONTRANSFER_ANDROID_KEY_PASSWORD`
in the environment, never command-line password arguments. Use `ANDROID_HOME`
or `PATH` to locate `apkanalyzer`, `zipalign` and `apksigner`; the default local
Buildozer SDK is also detected. Existing output APKs are never overwritten.

Old Buildozer SDK installations may contain an unusable `tools/bin/apkanalyzer`.
Install `cmdline-tools;latest` with the SDK's `sdkmanager` in that case; the signer
prefers `cmdline-tools/*/bin/apkanalyzer` within the selected SDK.

The signer checks embedded build identity, required contents, ARM64-only packaging,
package ID, SDK levels, versionName/versionCode, non-debuggable/non-test-only status,
share intent filters, alignment and the expected certificate. A debug APK cannot
be converted to a release by merely running the signing command.

## CI signed build

Open **Actions > Build Android artifact > Run workflow**:
select `main`, enable `signed_release`; leave `version_code` blank to use
`android/release.toml`, or supply a coordinated override for a manual test.
The build job runs tests and builds an unsigned release **without secrets**.
A separate fresh signing job uses the protected `android-signing` environment,
downloads only that run's unsigned artifact, signs and verifies it, and removes
the temporary keystore. It does not restore build caches or install dependencies.

Download `MoonTransfer-<version>-android-arm64.apk` and `SHA256SUMS` from that run
(14-day retention). The intermediate `android-release-unsigned` artifact expires
after one day and is **not installable**. CI versions include the run number and
commit; the versionCode is independent. For an exact local rebuild, use the same
commit, displayed version and versionCode. Signature identity is stable; byte-for-byte
reproducibility is not guaranteed. PRs, pushes to `main` and normal manual Android
runs still produce debug APKs and never access the signing environment.

## Desktop and Android together

For a non-publishing rehearsal, run **Build release artifacts** manually on `main`
with `signed_android` enabled. Both desktop and Android are built in the same run,
with the same version and commit; download the four desktop archives and signed
APK from its artifacts. This needs the real signing environment but creates no tag
or release. An optional `android_version_code` overrides the file only for this test.

Pushing a new `vX.Y.Z-alpha.N`, `-beta.N` or `-rc.N` tag triggers the desktop
workflow, which calls the reusable Android workflow at the same revision. Android
no longer has an independent tag trigger, avoiding duplicate builds and publishers.
The final job waits for every desktop build and Android signing, requires exactly
the four desktop packages plus `MoonTransfer-<version>-android-arm64.apk`, and
generates one `SHA256SUMS` covering all five. Debug/unsigned APKs and unexpected
versions are rejected. It creates or refreshes a draft pre-release and refuses to
overwrite an already published release. A failed build/signature or missing key
blocks the draft, instead of silently producing a desktop-only release.

Before each new tag, configure `android-signing`, test the manual combined run,
update `android/release.toml` if necessary, and merge through a PR. Tags must point
to a commit already included in `main`; the numeric tag version must match
`pyproject.toml`. Existing tags/releases are not modified by this change.

## Installation transition

The new key does not match existing debug installations. Normally uninstall the
prototype once before installing the first signed release; this deletes private
app data. Subsequent releases signed with this key can update each other with
the same application ID and valid versionCode, without that reset. Debug and
release currently share an application ID and cannot be installed side by side.
Do not distribute temporary-key test APKs as real releases.

## Test without the permanent key

After compiling an unsigned release, run the SDK integration test with its
identity. It creates a temporary key, tests signing locally and after a Base64
round trip, rejects a wrong fingerprint, and deletes all keys and signed test APKs:

```sh
MOONTRANSFER_SIGNING_TEST_APK="release/MoonTransfer-${version}-android-arm64-release-unsigned.apk" \
MOONTRANSFER_SIGNING_TEST_VERSION="$version" MOONTRANSFER_SIGNING_TEST_COMMIT="$commit" \
MOONTRANSFER_SIGNING_TEST_VERSION_CODE="$version_code" \
python3 -m unittest tests.test_android_signing -v
```

References: [Android app signing](https://developer.android.com/studio/publish/app-signing),
[apksigner](https://developer.android.com/tools/apksigner),
[GitHub environment protection](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

## Verify GitHub setup

Variable names and values must have no leading/trailing whitespace:
`ANDROID_KEY_ALIAS` must be exactly `moontransfer`, without quotes.
The fingerprint is public; passwords and the keystore are not.

```sh
gh secret list --env android-signing --repo gaumeloth/MoonTransfer
gh variable list --env android-signing --repo gaumeloth/MoonTransfer
gh variable get ANDROID_KEY_ALIAS --env android-signing --repo gaumeloth/MoonTransfer
```

These commands do not display secret values. A listed secret can still contain
an incorrect value: signing is the actual validation.
With one maintainer as reviewer, enabling `Prevent self-review` prevents that
person from approving their own runs; choose deliberately between independent
review and personal approval. Disable administrator bypass if configured
approval must be mandatory.

A waiting run needs environment approval from the Actions summary.
If signing fails, read the first job error, correct the alias/secrets as needed
and rerun failed jobs. If workflow or code changed, start a new run on the
correct revision: rerunning the old one does not automatically use new commits.

Before distributing, also test restoring the key backup to a separate private
location and verify its fingerprint with local tools.
Never upload backups or passwords as artifacts. For APK and checksum verification,
see [Troubleshooting](../docs/TROUBLESHOOTING.md#verify-downloads);
for the full sequence use the [release procedure](../docs/RELEASING.md#publication-procedure).

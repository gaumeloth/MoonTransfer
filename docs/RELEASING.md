# Artifacts and releases

[Italiano](RELEASING.it.md) | [MoonTransfer](../README.md)

## Contents

- [Desktop release artifacts](#desktop-release-artifacts)
- [Android test artifacts](#android-test-artifacts)
- [Desktop and Android release publication](#desktop-and-android-release-publication)
- [Publication procedure](#publication-procedure)
- [Protection and diagnosis](#protection-and-diagnosis)

## Desktop release artifacts

`.github/workflows/release-builds.yml` tests the same `onedir` packaging flow
on native GitHub-hosted runners. It currently covers:

- Linux x86_64 on Ubuntu 22.04;
- Windows x86_64 on Windows Server 2022;
- macOS x86_64 on an Intel runner;
- macOS ARM64 on an Apple Silicon runner.

Every job installs the pinned workflow version of `uv` and Python 3.13, checks
`uv.lock`, installs locked dependencies, runs the full unit test suite, fetches
the checksum-verified `croc` binary, builds MoonTransfer, validates the bundled
`croc` version, and creates a downloadable archive.

On Linux, the runner installs Qt's complete XCB/XKB dependency set before
building. Package validation rejects an incomplete native runtime, and an X11
smoke test starts the packaged executable and injects keyboard input. This
prevents artifacts from silently mixing bundled Qt keyboard libraries with
incompatible versions from the destination system.

Linux and macOS artifacts use `tar.gz` so executable permissions and symbolic
links are preserved. Windows uses ZIP. The macOS archive contains a
`MoonTransfer.app` bundle, while the other platforms retain the normal
PyInstaller `onedir` layout. Every archive also contains `LICENSE`,
`THIRD_PARTY_NOTICES.md`, both READMEs, the contributor and technical guides,
Android guides, and their linked license texts and logo. Relative paths are
preserved so local links also work after extraction. The explicit allowlist in
`tools/package_release.py` excludes unrelated sources and private files.

Pull requests, pushes to `main`, and manual workflow runs create test artifacts
without publishing a release. Non-tagged builds use a `dev` version containing
the workflow run number and commit prefix. The artifacts are available from the
workflow run summary for 14 days and can be downloaded for manual testing on
the target systems. The same full version and commit are embedded in the
application's diagnostic summary.

## Android test artifacts

`.github/workflows/android-build.yml` provides a separate native Linux build for
the Android prototype. Its debug path runs for pull requests, pushes to `main`,
and normal manual dispatches. Pre-release tags call its signed path from the
main release workflow. The job uses pinned versions of `uv`, Python
3.13.14, Java 17, Go 1.25.12, and Rust 1.97.1; checks the Android lock file;
installs the locked Android build environment; runs the Android-specific tests
and host diagnostics; and builds the ARM64 debug APK. Android SDK/NDK and Gradle
downloads are cached, while the large python-for-android native build is
deliberately not cached until the workflow has enough real timing and
reliability data. A dedicated Buildozer `ci` profile accepts the configured SDK
licenses non-interactively; normal local builds retain the interactive prompt.

Before upload, MoonTransfer checks the APK archive for unsafe or duplicate
entries, verifies the expected ARM64 native libraries and generated application
files, rejects source-only assets, and compares the embedded build version,
commit, `croc` version, and MoonTransfer protocol version with the current CI
build. The workflow also uses Android's `aapt` to verify the application ID,
version name and code, SDK bounds, debug status, and declared native
architecture. The raw, versioned APK is available from the workflow run summary
for 14 days, without an additional ZIP wrapper.

This APK is a test artifact, not an Android release: it is not attached to the
GitHub Releases page and it is not signed with a project-controlled release key.
Buildozer uses a debug signing identity that can differ between a local build
and GitHub-hosted runners. Android may therefore refuse to install one over the
other; uninstalling the existing prototype first resolves that signature
mismatch but also removes its private application data.

## Desktop and Android release publication

Release publication is deliberately more restrictive:

- only tags such as `v0.1.0-alpha.1`, `v0.1.0-beta.1`, or `v0.1.0-rc.1`
  trigger the release job;
- the numeric base of the tag must match `[project].version` in
  `pyproject.toml`;
- the tag commit must already belong to `main`;
- every desktop build and the signed Android build must complete before the
  release job starts; missing signing configuration blocks the draft;
- the workflow requires four desktop archives and the signed ARM64 APK, then
  generates one `SHA256SUMS` covering all five;
- GitHub creates a draft marked as a pre-release, never an immediately
  published release;
- a rerun may refresh an existing draft but refuses to overwrite a published
  release.

The project is currently in the alpha phase: core behavior and distribution
are still being expanded and validated. Move to beta only when the feature set
planned for the first stable release is complete and development is primarily
focused on compatibility, usability fixes, and stabilization. Stable tags are
intentionally not accepted by the current workflow.

## Publication procedure

1. Configure [Android signing](../android/SIGNING.md) and verify a combined manual run on `main` using **Build release artifacts > signed_android**. This creates no tag or release.
2. On a topic branch, increase `android/release.toml` beyond every versionCode already distributed, including manual builds. If the numeric base changes, update `[project].version` and `uv.lock`. Update release notes and documentation.
3. Run checks, open a PR to `main`, and wait for the merge. Uncommitted changes do not become part of a tag.
4. Run `git fetch origin`, return to `main` with `git switch main`, then run `git merge --ff-only origin/main`. Check the branch, commit and `git status --short`: no intended release changes should remain unmerged.
5. Choose a **new** annotated tag matching `vX.Y.Z-alpha.N`, `vX.Y.Z-beta.N` or `vX.Y.Z-rc.N`; its numeric base must match `pyproject.toml`. Check `git tag --list` and `git ls-remote --tags origin` to ensure it does not already exist.
6. Replace `NEW_TAG` with that value, then run `git tag -a NEW_TAG -m "MoonTransfer NEW_TAG"` and `git push origin NEW_TAG`. Do not use the placeholders literally.
7. Wait for all four desktop builds and Android signing. Approve protected environment jobs when requested, then inspect the draft.
8. Download all five packages and `SHA256SUMS`; [verify downloads](TROUBLESHOOTING.md#verify-downloads), inspect version/commit and bundled documents, and test transfers on real devices.
9. Publish the draft manually only after testing. Never move distributed tags or overwrite published releases: fix through a PR and use the next tag.

## Protection and diagnosis

Signing uses `android-signing`; draft creation uses a separate `release`
environment. Configure the latter before the first tag, with pre-release tag
rules and reviewers according to project policy. Do not copy Android keys there:
publication uses `GITHUB_TOKEN` with `contents: write`, while signing stays in
its own job.

A job waiting for approval is not a failed build. Check the requested environments
in the run summary. The combined manual rehearsal verifies builds and signing,
but does not execute the tag-only draft creation job.
Do not work around a failed run by publishing a desktop-only release.

Configure environment rules in [GitHub settings](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

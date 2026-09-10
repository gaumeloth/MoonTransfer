# Contributing to MoonTransfer

[Italiano](CONTRIBUTING.it.md) | [MoonTransfer](README.md)

## Contents

- [Project status and roadmap](#project-status-and-roadmap)
- [Design constraints](#design-constraints)
- [Contribution model](#contribution-model)
- [Bug reports and technical logs](#bug-reports-and-technical-logs)
- [Contributor workflow](#contributor-workflow)
- [Documentation maintenance](#documentation-maintenance)
- [Orientation](#orientation)
- [Development setup](#development-setup)
- [Python version policy](#python-version-policy)
- [Dependency changes](#dependency-changes)
- [Development run](#development-run)
- [Automatic tests](#automatic-tests)
- [Testing expectations by change type](#testing-expectations-by-change-type)
- [Manual transfer test](#manual-transfer-test)
- [Before committing](#before-committing)
- [Maintenance tasks](#maintenance-tasks)
- [Generated files](#generated-files)
- [Documentation checks](#documentation-checks)

## Project status and roadmap

MoonTransfer is in active early development. It already provides a graphical
send/receive flow, bundles a pinned and checksum-verified `croc` binary during
builds, includes unit tests for the non-GUI logic, and publishes native
pre-built alpha archives for the main platforms. The current public line is
`v0.1.0-alpha.3`. Android is a functional but experimental target with debug and signed builds for
files, folders, and mixed selections, not a supported end-user release.

Possible future improvements, in indicative order:

- collect feedback from `alpha.3` and continue validating the automated
  `onedir` artifacts on their target systems;
- continue hardening the Kivy Android target, especially lifecycle edge cases,
  large or deeply nested payloads, device and document-provider coverage, and
  release packaging, before treating Android as a supported platform;
- add signing and notarization where appropriate, then evaluate more native
  distribution formats such as AppImage, a Windows installer, and a macOS disk
  image;
- add advanced settings for custom `croc` relays;
- reduce the remaining large desktop and Android orchestration modules when a
  concrete ownership boundary justifies the split;
- extend automatic coverage for packaging metadata, platform-specific behavior,
  transfer failures, and Android lifecycle recovery;
- run the latest-`croc` compatibility check automatically on the main
  platforms.

The guiding idea is to stay close to the Unix philosophy: MoonTransfer should
do one thing, delegate well to `croc`, keep behavior readable, and avoid hiding
errors unnecessarily.

## Design constraints

Contributions should preserve the current scope of the project:

- MoonTransfer is a graphical wrapper around `croc`, not a replacement for it.
  File transfer, relay negotiation, encryption, and the final data channel
  should remain delegated to `croc` unless there is a strong reason to do
  otherwise.
- Avoid adding mandatory external services. The normal transfer flow should not
  require a MoonTransfer-owned server or account system.
- Keep `croc` command construction centralized in `src/moontransfer/croc.py`.
  This makes transfer flags, environment handling, and command previews easier
  to audit.
- Start external commands through structured process APIs, not through shell
  strings. Desktop uses `QProcess`; Android uses `subprocess.Popen`, which avoids depending on
  bash, fish, PowerShell, or platform-specific quoting rules.
- Prefer clear errors and visible technical output over silently hiding failures.
  The GUI can present friendly messages, but the technical details should still
  help diagnose `croc`, network, packaging, and desktop-integration problems.
- Keep local builds reproducible. Normal builds should use the committed
  `uv.lock`, the pinned `croc` version, and the SHA-256 hashes declared in
  `pyproject.toml`.
- Do not commit generated files or bundled binaries such as `dist/`, `build/`,
  `.venv/`, cache directories, or `third_party/croc/`.

## Contribution model

External contributions should be proposed through pull requests. Direct push
access to the original repository is not expected.

Recommended Git workflow:

1. fork the repository on GitHub;
2. clone your fork locally;
3. add the original repository as `upstream`;
4. create a topic branch for the change;
5. commit a focused set of changes;
6. push the branch to your fork;
7. open a pull request from your fork branch to `gaumeloth/MoonTransfer:main`.

Example:

```sh
git clone https://github.com/<your-user>/MoonTransfer.git
cd MoonTransfer
git remote add upstream https://github.com/gaumeloth/MoonTransfer.git
git switch -c short-change-description
```

Before starting new work, update your local `main` from the original
repository:

```sh
git fetch upstream
git switch main
git merge --ff-only upstream/main
```

Keep pull requests focused. If a change mixes unrelated code, documentation,
formatting, dependency, and build changes, split it before opening the pull
request. Larger changes should be discussed before implementation.

## Bug reports and technical logs

Useful bug reports should make the problem reproducible without exposing private
transfer information.

When reporting a problem, include:

- the operating system and version for the sender and receiver when both are
  involved;
- whether MoonTransfer was started with `uv run moontransfer` or from the
  packaged `dist/MoonTransfer/` bundle;
- the branch, commit, or release used;
- whether the bundle was rebuilt after the latest code change or branch switch;
- the exact steps that led to the problem;
- what you expected to happen and what actually happened;
- relevant messages from the GUI technical details panel or terminal output.

Do not paste complete transfer codes, raw `CROC_SECRET` values, or private file
paths unless they are necessary and safe to share. MoonTransfer logs short
`code-id` values for internal transfer codes; those are usually safer to share
than full codes.

For transfer failures, include logs from both sides when possible. It is useful
to state which side was sending, which side was receiving, whether both builds
came from the same commit, and whether a firewall, VPN, proxy, or corporate
network could be involved.

## Contributor workflow

For a normal development session:

1. prepare the development environment;
2. fetch the pinned `croc` binary;
3. run MoonTransfer and make your change;
4. run the automatic checks;
5. run a manual transfer test if the change affects transfer behavior or the
   GUI flow;
6. commit only source, documentation, configuration, and lockfile changes that
   are intentional;
7. push the branch to your fork and open a pull request.

If you change user or contributor documentation, update both language versions
of the affected guide: they need the same structure and information, not a
literal translation. Keep the root READMEs focused on user entry points.

If you test the packaged application in `dist/`, rebuild it after code changes
or after switching branches. The generated bundle is not updated automatically
and may still contain older code.

## Documentation maintenance

User and contributor documentation should change together with the behavior it
describes. A pull request should update the relevant English and Italian guides
when it changes:

- user-visible workflows, labels, dialogs, warnings, or error messages;
- installation, prerequisite, build, or startup commands;
- supported Python versions, dependency management, or `uv.lock` handling;
- `croc` command arguments, transfer-code handling, relay behavior, metadata
  flow, or transfer verification;
- generated files, repository layout, ignored paths, or packaging behavior;
- test commands, manual verification steps, or contributor workflow;
- license information or bundled third-party components.

Each language pair should keep the same section order and the same facts. They
do not need to be word-for-word translations: prefer clear wording for each
language, especially where a literal translation would be awkward.

When documenting commands, keep examples copy-pasteable and check that paths,
script names, and flags exist in the repository. Avoid documenting planned
behavior as if it already exists; future ideas belong in the roadmap or in an
issue.

## Orientation

The [build guide](docs/BUILD.md) covers initial host setup. Use the [architecture map](docs/ARCHITECTURE.md) to choose the module to change and the [release guide](docs/RELEASING.md) for CI and distribution. All changes to `main`, including maintainer changes, go through pull requests.

## Development setup

Prepare the Python environment with the locked dependencies and the development
tools needed for build-related work:

```sh
uv sync --frozen --dev
```

Download the pinned `croc` binary used by the development run:

```sh
uv run python tools/fetch_croc.py
```

`tools/fetch_croc.py` downloads the pinned `croc` release declared in
`pyproject.toml`, verifies the archive checksum, and copies the binary into
`third_party/croc/`.

## Python version policy

Python compatibility is declared in two places:

- `pyproject.toml`, through `requires-python`;
- `.python-version`, used by tools such as `uv` to select a compatible runtime.

Keep both files aligned. At the moment MoonTransfer supports Python
`>=3.13,<3.15`, meaning Python 3.13.x and 3.14.x are accepted.

If the supported Python range changes:

1. update `requires-python` in `pyproject.toml`;
2. update `.python-version` with the same range;
3. update the Python instructions in both language versions of the build and contributor guides;
4. run `uv lock` if dependency resolution can be affected;
5. run `uv sync --frozen --dev`;
6. run the automatic checks;
7. run a build if the change can affect packaging.

Do not narrow the supported Python range without a concrete reason, such as a
dependency constraint, an unsupported Python release, or a runtime behavior that
cannot be handled cleanly.

## Dependency changes

`uv.lock` is committed intentionally. It makes dependency resolution
reproducible for development, tests, and local builds.

If you change Python dependencies:

1. edit `pyproject.toml`;
2. update `uv.lock` with `uv lock`;
3. run `uv sync --frozen --dev`;
4. run the automatic checks;
5. commit both `pyproject.toml` and `uv.lock`.

Do not edit `uv.lock` manually.

## Development run

Start MoonTransfer from the project root:

```sh
uv run moontransfer
```

Useful references:

- [`croc`](https://github.com/schollz/croc), transfer engine;
- [`uv`](https://docs.astral.sh/uv/), Python environment and dependency
  management;
- [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/), GUI toolkit;
- [PyInstaller](https://pyinstaller.org/en/stable/), bundle creation;
- [Pillow](https://pillow.readthedocs.io/en/stable/), build-time conversion of
  the application icon.

## Automatic tests

Unit tests cover the non-GUI logic split across the runtime modules and
maintenance tools: payload inventory and exact-tree verification, protocol
validation, command construction, transfer output parsing, user-facing status
messages, desktop integration helpers, process-output splitting, pinned `croc`
asset selection, build-identity validation and generation, release-archive
packaging, and latest-release check helpers.

They also cover simulated Qt widget events, but do not replace manual GUI interaction and they do not perform a real file
transfer by default. Use the manual transfer test for that.

Run the unit test suite:

```sh
uv run --frozen python -m unittest discover -s tests
```

Check that the Python modules compile:

```sh
uv run --frozen python -m compileall -q src/moontransfer tools
```

## Testing expectations by change type

Use the smallest test set that covers the risk of the change, then broaden it
when the behavior crosses module or platform boundaries.

- Documentation-only changes: run `git diff --check`. If the documentation
  describes commands or paths, also verify them against the repository.
- Changes to build identity, version propagation, PyInstaller data files, or
  release workflow versioning: run `tests/test_build_info.py`,
  `tests/test_build_metadata.py`, `tests/test_package_release.py`, and a local
  bundle build.
- Changes to `croc` arguments, `CROC_SECRET`, command previews, or isolated
  configuration: run `tests/test_croc.py`, `tests/test_check_latest_croc.py`,
  and the full unit test suite.
- Changes to metadata JSON, generated codes, filename validation, hash
  validation, manifests, or protocol versioning: run `tests/test_protocol.py`,
  `tests/test_payload.py`, and `tests/test_files.py`.
- Changes to source scanning, destination handling, overwrite/rename behavior,
  hashing, received-tree verification, or final placement: run
  `tests/test_payload.py` and `tests/test_files.py`, then perform a manual
  receive test.
- Changes to progress parsing or displayed transfer statistics: run
  `tests/test_progress.py` with representative `croc` output samples.
- Changes to user-facing status text: run `tests/test_messages.py` and check the
  GUI wording manually.
- Changes to process lifecycle, stdin replies, cancellation, or stdout/stderr
  parsing: run `tests/test_runner.py` and perform a manual transfer test.
- Changes to opening folders or desktop integration: run `tests/test_desktop.py`
  and manually test the affected platform if possible.
- Changes to `tools/fetch_croc.py`, `tools/check_latest_croc.py`, pinned `croc`
  versions, or release hashes: run the related tool tests and the latest-`croc`
  check when network access is available.
- Changes to build wrappers, PyInstaller configuration, or packaged resources:
  run the build script for the affected platform and start the generated bundle
  from `dist/MoonTransfer/`.
- Changes to Android source preparation, Buildozer configuration, the native
  `croc` recipe, or APK packaging: check `android/uv.lock`, run the Android test
  subset and `./scripts/android.sh doctor`, then build and package a local APK
  when the toolchain or final package is affected.
- Changes to the main transfer flow or GUI coordination: run the full unit test
  suite, start MoonTransfer manually, and perform a manual transfer test.

## Manual transfer test

To verify the full flow during development, you can use two MoonTransfer
instances on the same machine:

1. open two MoonTransfer instances;
2. in the first instance, select a small file and a folder containing a nested
   file and an empty folder;
3. copy the displayed code;
4. in the second instance, receive into a different folder;
5. check that the `MoonTransfer` container contains every selected root, nested
   file, and empty folder.

This test is useful for development, but it is not the main use case of the
program, which remains transferring between two different computers.

## Before committing

Run these checks before committing:

```sh
uv lock --check
uv run --frozen python -m unittest discover -s tests
uv run --frozen python -m compileall -q src/moontransfer tools
git diff --check
```

If you touch build scripts, packaging, or `MoonTransfer.spec`, also run the
build script for the platform you changed.

For Android-specific changes, also run:

```sh
uv lock --check --project android
PYTHONPATH="$PWD/src" uv run --project android --frozen --group build \
  python -m unittest discover -s tests -p 'test_android*.py' -v
./scripts/android.sh doctor
```

Build and package a local APK as well when changing the Android toolchain,
generated source allowlist, native recipe, or final package validation.

## Maintenance tasks

### Check the latest croc release

Normal builds are intentionally reproducible: they use the `croc` version and
SHA-256 hashes pinned in `pyproject.toml`. Contributors can separately check
whether a newer upstream `croc` release is available and whether MoonTransfer
still uses it correctly.

From the project root:

```sh
uv run --frozen python tools/check_latest_croc.py
```

The command:

- reads the pinned `croc` version from `pyproject.toml`;
- asks GitHub for the latest upstream `croc` release;
- stops immediately if the pinned version is already current;
- if a newer version exists, downloads the release checksum file and the
  current-platform archive;
- verifies the archive SHA-256 before extraction;
- runs smoke checks for the `croc` flags used by MoonTransfer.

To run the smoke checks even when the latest release is already the pinned one:

```sh
uv run --frozen python tools/check_latest_croc.py --force
```

There is also an optional end-to-end transfer check:

```sh
uv run --frozen python tools/check_latest_croc.py --force --transfer
```

The transfer check runs three short sessions with the latest `croc` binary:
automatic receive with the flags used for metadata, prompted acceptance with
the flags used for the main payload, and prompted rejection. The accepted
sessions transfer multiple roots including a nested folder, an empty folder,
and a Unicode filename, then verify the received content. The rejected session
checks that no destination content is created. These checks require Internet
access and a reachable `croc` relay, so they are intentionally not part of the
default check.

To compare the latest release with an older `croc` version in both transfer
directions, add `--compat-version`:

```sh
uv run --frozen python tools/check_latest_croc.py --force --transfer \
  --compat-version 10.7.0
```

This runs the normal latest-to-latest checks first, then tests the older sender
against the latest receiver and the latest sender against the older receiver.
The command exits with a non-zero status if any pair fails. For `croc 11.x`
against `10.x`, that failure is the expected result of the intentional PAKE
protocol break described in [Transport compatibility](README.md#transport-compatibility),
not evidence of a MoonTransfer regression.

If the check passes for a new release, update `[tool.moontransfer.croc]` in
`pyproject.toml` with the new version and official hashes, then run the normal
test suite before committing.

## Generated files

These paths are generated locally and should not be committed:

```text
.venv/
.cache/
android/.buildozer/
android/.venv/
build/
dist/
release/
third_party/croc/
__pycache__/
```

If one of these paths appears in `git status`, leave it out of the commit.

## Documentation checks

Keep English/Italian pairs aligned in `docs/`, `CONTRIBUTING` and Android guides
as well as the root READMEs. Keep READMEs as entry points and avoid duplicating
full procedures across guides. Check labels against actual widgets and do not
hardcode test counts. Development commands use checkout-root paths, not paths
relative to the document directory.

`tests/test_documentation.py` checks local links and anchors in the formats used
by this project, translation counterparts and documents included in archives.
It does not check external site availability or instruction correctness: these
still need review. When adding a guide, update `RELEASE_DOCUMENT_NAMES` in
`tools/package_release.py` and navigation links. Never include working
directories, keys or generated files.

```sh
uv run --frozen python -m unittest tests.test_documentation tests.test_package_release -v
```

For opt-in Android GUI tests, use the command in the [Android guide](android/README.md#local-gui-tests).

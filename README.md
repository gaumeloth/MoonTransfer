# MoonTransfer

Italian version: [README.it.md](README.it.md)

MoonTransfer is a GUI for sending and receiving files through
[`croc`](https://github.com/schollz/croc).

Its goal is to make file transfer simple: the sender chooses a file,
MoonTransfer shows a code, and the receiver enters that code to save the file
in the selected folder.

MoonTransfer does not implement its own cryptographic protocol. Security,
connection handling, and transfer are provided by `croc`; MoonTransfer only
provides the graphical interface and includes the `croc` binary in the built
application.

## Current status

MoonTransfer is in an early stage. The main flow is already working:

- sending a single file;
- receiving file metadata through a code before accepting the main download;
- using `croc`'s native accept/reject prompt for the main transfer;
- showing `croc` output in the GUI;
- generating one user-facing code while keeping internal control codes hidden;
- showing filename, size, and SHA-256 before downloading the main file;
- local build with PyInstaller;
- automatic download of the `croc` binary during the build;
- pinned `croc` version and SHA-256 verification for supported platforms;
- final bundle with `croc` included.

The project does not currently provide signed installers or ready-made release
packages. To use it, you need to download the source code and build it locally
for your operating system.

The build produces a portable `MoonTransfer` folder: to move it to another
computer, copy the whole generated folder, not just the executable.

## Quick guide

To use MoonTransfer today, follow these steps in order:

1. download the source code, with Git or as a ZIP archive;
2. open a terminal in the project folder;
3. install `uv`;
4. let `uv` find or install Python 3.13.x/3.14.x;
5. run the build script for your operating system;
6. open the `dist/MoonTransfer/` folder;
7. start MoonTransfer.

You do not need to install `croc` manually: it is downloaded automatically
during the build.

## Download the source

The project repository is:

```text
https://github.com/gaumeloth/MoonTransfer
```

You can download MoonTransfer in two ways:

- with Git, recommended if you want to update the repository easily or
  contribute;
- as a ZIP archive, simpler if you only want to try or build the program
  without using Git.

Expand only the method you want to use.

<details>
<summary>Download with Git</summary>

If you do not have Git, install it first from the
[official download page](https://git-scm.com/downloads/).

Operating-system-specific instructions are collapsed by default: expand only
the one for the system you are using.

<details>
<summary>Linux</summary>

On Linux, you can use your distribution package manager, for example:

```sh
sudo pacman -S git          # Arch Linux
sudo apt install git        # Debian, Ubuntu, and derivatives
sudo dnf install git        # Fedora
```

</details>

<details>
<summary>macOS</summary>

On macOS, you can install Apple's command line tools by running:

```sh
git --version
```

If Git is not present, macOS will offer to install the Command Line Tools.
Alternatively, you can use Homebrew:

```sh
brew install git
```

</details>

<details>
<summary>Windows</summary>

On Windows, download Git from the
[official Windows page](https://git-scm.com/download/win), start the installer,
and use these choices:

- download the regular installer for your architecture, usually **64-bit Git
  for Windows Setup** on Intel/AMD PCs;
- keep the default components;
- at the `PATH` step, select **Git from the command line and also from
  3rd-party software**, so `git` also works from PowerShell;
- for editor, line endings, terminal, HTTPS, and extra options, you can keep
  the defaults;
- Git Credential Manager can stay enabled; it is useful if you later work with
  private repositories.

</details>

After installation, close and reopen the terminal, then verify:

```sh
git --version
```

Download the repository:

```sh
git clone https://github.com/gaumeloth/MoonTransfer.git
cd MoonTransfer
```

From now on, run all following commands from inside the `MoonTransfer` folder.

</details>

<details>
<summary>Download as a ZIP archive</summary>

This method does not require Git.

1. Open the [project GitHub page](https://github.com/gaumeloth/MoonTransfer).
2. Press **Code**.
3. Choose **Download ZIP**.
4. Extract the archive into a folder.
5. Open the extracted folder.

The extracted folder may be named `MoonTransfer-main` instead of
`MoonTransfer`. That is fine: use that folder for the following commands.

Now open a terminal inside the extracted folder.

<details>
<summary>Linux/macOS</summary>

You can use the file manager and choose **Open in terminal**, or open a
terminal and manually move into the extracted folder with `cd`.

</details>

<details>
<summary>Windows</summary>

Open the extracted folder in File Explorer. Then use one of these methods:

- right-click an empty area of the folder and choose **Open in Terminal**;
- or click the path bar, type `powershell`, and press Enter.

</details>

GitHub also documents source archive downloads in its
[official documentation](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives).

</details>

## Prepare the system

To create the build, you need:

- [`uv`](https://docs.astral.sh/uv/);
- Python 3.13.x or 3.14.x, installed manually or managed by `uv`;
- Internet access during the build;
- a platform supported by `tools/fetch_croc.py`: Linux x86_64/ARM64, macOS
  Intel/Apple Silicon, or Windows x64/ARM64.

The simplest approach is to install `uv` and let `uv` manage Python for the
project.

### Install uv

The official `uv` documentation is available at
[docs.astral.sh/uv](https://docs.astral.sh/uv/). Updated installation
instructions are on the
[Installing uv](https://docs.astral.sh/uv/getting-started/installation/) page.

Expand only the operating system you are using.

<details>
<summary>Arch Linux</summary>

```sh
sudo pacman -S uv
```

</details>

<details>
<summary>Linux/macOS</summary>

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If the `uv` command is not found after installation, close and reopen the
terminal.

</details>

<details>
<summary>Windows PowerShell</summary>

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After installation, close and reopen PowerShell.

</details>

Verify the installation:

```sh
uv --version
```

### Prepare Python

MoonTransfer requires Python 3.13.x or 3.14.x. `uv` can use a version already
installed on the system or install a compatible one.

From the project folder, check which Python is found:

```sh
uv python find --show-version
```

If the command shows version `3.13.x` or `3.14.x`, you can continue.

If the command fails, or does not find a compatible version, run:

```sh
uv python install '>=3.13,<3.15'
```

Then try again:

```sh
uv python find --show-version
```

If you prefer to install Python manually, choose a stable Python 3.13 or 3.14
version from the
[official download page](https://www.python.org/downloads/).

<details>
<summary>Windows: install Python manually</summary>

On Windows, you have two practical options.

The first is the **Python install manager**, recommended by the recent official
documentation. Download it from the Python page, install it, open PowerShell,
and then install a compatible runtime:

```powershell
py install 3.14
```

Alternatively, you can install Python 3.13:

```powershell
py install 3.13
```

If the setup offers to add Python to `PATH`, accept it: this makes PowerShell
usage simpler.

The second option is the classic installer for a single Python release:

- on the Windows release page, choose **Windows installer (64-bit)** on modern
  Intel/AMD PCs, or **Windows installer (ARM64)** on Windows ARM;
- do not choose the **embeddable package**, because it is meant for embedding
  Python in other applications, not for terminal usage;
- on the first screen, enable **Add python.exe to PATH**;
- use **Install Now** for a standard installation, or **Customize
  installation** only if you want to review the options;
- if you use the custom screen, leave `pip`, `py launcher`, and the standard
  files enabled;
- if **Disable path length limit** appears at the end, you can enable it: it is
  not required for MoonTransfer, but it reduces possible long-path limits in
  other Python projects.

After installation, close and reopen PowerShell, then verify:

```powershell
python --version
py --version
```

One of the available versions must be Python 3.13.x or 3.14.x. If Windows opens
the Microsoft Store instead of Python, check **Manage app execution aliases**
and disable any Store Python aliases that interfere with the real installation.

</details>

## Create the build

The build installs Python dependencies, downloads the `croc` binary for the
current platform, and creates the PyInstaller package in `dist/`.

The `croc` version and expected SHA-256 hashes are declared in
`[tool.moontransfer.croc]` in `pyproject.toml`. A normal build uses that pinned
version; it does not automatically switch to the latest upstream `croc`
release.

Use the script for your operating system. The scripts check the main
prerequisites, run `uv sync --frozen --dev` using the committed `uv.lock`, and
then call `tools/build.py`.

<details>
<summary>Linux/macOS</summary>

From the project folder:

```sh
./scripts/build.sh
```

You can launch the command from fish, bash, or zsh as `./scripts/build.sh`.
Do not run it as `fish scripts/build.sh`.

If the build completes successfully, the program will be in:

```text
dist/MoonTransfer/
```

</details>

<details>
<summary>Windows</summary>

Open PowerShell in the project folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

If the build completes successfully, the program will be in:

```text
dist\MoonTransfer\
```

</details>

<details>
<summary>Advanced method</summary>

The common command, valid on all systems after preparing the environment with
`uv sync --frozen --dev`, is:

```sh
uv run --frozen --dev python tools/build.py
```

`tools/build.py` is the build orchestrator: it runs `tools/fetch_croc.py` and
then PyInstaller using `MoonTransfer.spec`.

To check the latest upstream `croc` release without changing the build pin:

```sh
uv run --frozen python tools/fetch_croc.py --latest
```

</details>

## Start MoonTransfer

After the build, open the generated folder:

```text
dist/MoonTransfer/
```

Do not move only the executable: it must remain next to the files and folders
generated by PyInstaller.

<details>
<summary>Linux</summary>

From the file manager, open `dist/MoonTransfer/` and start the `MoonTransfer`
file.

If the file manager does not start it with a double click, you can use the
terminal:

```sh
./dist/MoonTransfer/MoonTransfer
```

</details>

<details>
<summary>macOS</summary>

Open the folder generated by the build and start the `MoonTransfer` executable.

If macOS blocks the app because it is not signed, open it from the system
security settings, or start it from the terminal from the project folder:

```sh
./dist/MoonTransfer/MoonTransfer
```

</details>

<details>
<summary>Windows</summary>

Open:

```text
dist\MoonTransfer\
```

and double-click:

```text
MoonTransfer.exe
```

</details>

## Troubleshooting

### Qt SVG icon warnings on Linux

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

## Use MoonTransfer

To complete a transfer, you need two people or two computers:

- the sender opens the **Invia** (Send) tab and generates a code;
- the receiver opens the **Ricevi** (Receive) tab and enters that code.

Both computers must be connected to the Internet. The code must be shared
outside MoonTransfer, for example via chat, phone, or email.

### Send a file

On the computer that has the file to send:

1. open MoonTransfer;
2. go to the **Invia** (Send) tab;
3. press **Sfoglia...** (Browse);
4. choose the file to send;
5. press **Invia** (Send);
6. wait for the code to appear;
7. share the code with the person who needs to receive the file.

The code first lets the receiver download a small metadata file. After that,
MoonTransfer opens the main `croc` transfer and waits for the receiver to accept
or reject it through `croc`'s native prompt.

During the main file transfer, MoonTransfer shows progress, transferred size,
current speed, elapsed time, and estimated remaining time when `croc` provides
enough progress information.

The code is one-time use: it is valid for that transfer and should not be
reused.

### Receive a file

On the computer that needs to receive the file:

1. open MoonTransfer;
2. go to the **Ricevi** (Receive) tab;
3. paste the received code;
4. choose the destination folder;
5. press **Ricevi** (Receive);
6. review the filename, size, and SHA-256 hash shown by MoonTransfer;
7. accept or reject the transfer;
8. if a file with the same name already exists, choose whether to skip,
   overwrite, or save the incoming file with another name;
9. wait for the transfer to complete.

The main file is downloaded only after MoonTransfer accepts `croc`'s main
transfer prompt. If you reject the transfer, MoonTransfer connects only to
refuse the main transfer and does not download the file content. At the end
MoonTransfer verifies the received size and SHA-256 hash before saving the file
in the final destination.

During the main file transfer, MoonTransfer shows progress, downloaded size,
current speed, elapsed time, and estimated remaining time when `croc` provides
enough progress information.

If the transfer does not start, check that both computers are connected to the
Internet and that any firewall or corporate network is not blocking the
connections used by `croc`.

## For contributors

### Project status and roadmap

MoonTransfer is in active early development. It already provides a graphical
send/receive flow, bundles a pinned and checksum-verified `croc` binary during
builds, and includes unit tests for the non-GUI logic. Ready-made releases are
not published yet, so users currently build the application locally.

Possible future improvements, in indicative order:

- publish ready-made releases for Linux, Windows, and macOS;
- add drag and drop for the file to send;
- support sending folders from the GUI;
- remember the last destination folder used;
- add advanced settings for custom `croc` relays;
- further separate transfer, progress parsing, and graphical interface code;
- add more automatic tests for output parsing, `croc` arguments, and error
  handling;
- add a CI pipeline to check builds and tests on the main platforms;
- run the latest-`croc` compatibility check automatically on the main
  platforms.

The guiding idea is to stay close to the Unix philosophy: MoonTransfer should
do one thing, delegate well to `croc`, keep behavior readable, and avoid hiding
errors unnecessarily.

### Design constraints

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
  strings. The application currently uses `QProcess`, which avoids depending on
  bash, fish, PowerShell, or platform-specific quoting rules.
- Prefer clear errors and visible technical output over silently hiding failures.
  The GUI can present friendly messages, but the technical details should still
  help diagnose `croc`, network, packaging, and desktop-integration problems.
- Keep local builds reproducible. Normal builds should use the committed
  `uv.lock`, the pinned `croc` version, and the SHA-256 hashes declared in
  `pyproject.toml`.
- Do not commit generated files or bundled binaries such as `dist/`, `build/`,
  `.venv/`, cache directories, or `third_party/croc/`.

### Contribution model

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

### Bug reports and technical logs

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

### Contributor workflow

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

If you change user or contributor documentation, keep `README.md` and
`README.it.md` aligned: they do not need to be literal translations, but they
should keep the same structure and the same information.

If you test the packaged application in `dist/`, rebuild it after code changes
or after switching branches. The generated bundle is not updated automatically
and may still contain older code.

### Documentation maintenance

User and contributor documentation should change together with the behavior it
describes. A pull request should update both `README.md` and `README.it.md` when
it changes:

- user-visible workflows, labels, dialogs, warnings, or error messages;
- installation, prerequisite, build, or startup commands;
- supported Python versions, dependency management, or `uv.lock` handling;
- `croc` command arguments, transfer-code handling, relay behavior, metadata
  flow, or transfer verification;
- generated files, repository layout, ignored paths, or packaging behavior;
- test commands, manual verification steps, or contributor workflow;
- license information or bundled third-party components.

The two README files should keep the same section order and the same facts. They
do not need to be word-for-word translations: prefer clear wording for each
language, especially where a literal translation would be awkward.

When documenting commands, keep examples copy-pasteable and check that paths,
script names, and flags exist in the repository. Avoid documenting planned
behavior as if it already exists; future ideas belong in the roadmap or in an
issue.

### Future CONTRIBUTING.md

For now, the README is the canonical contributor guide. This keeps the project
small and avoids splitting essential setup instructions across multiple files.

If the contributor documentation becomes too large, it can be moved into a
separate `CONTRIBUTING.md`. In that case:

- keep the user-facing README focused on download, build, startup, usage,
  troubleshooting, license, and a short contributor entry point;
- move detailed pull request workflow, testing policy, architecture notes, and
  maintenance tasks into `CONTRIBUTING.md`;
- link `CONTRIBUTING.md` from both README files;
- keep English and Italian documentation aligned, either with equivalent
  translated files or with a clear note about which file is authoritative.

### Where to change things

Use the existing module boundaries when choosing where to make a change:

- `src/moontransfer/app.py`: application entry point, main window, send tab,
  receive tab, high-level GUI flow, user dialogs, and coordination between
  transfer steps.
- `src/moontransfer/widgets.py`: reusable Qt widgets such as the status label,
  technical output panel, terminal-like output view, and transfer progress
  widget.
- `src/moontransfer/croc.py`: `croc` executable discovery, command arguments,
  transfer-code environment variables, isolated `croc` configuration, and safe
  command previews for logs.
- `src/moontransfer/protocol.py`: MoonTransfer control metadata format, protocol
  version, generated codes, filename validation, SHA-256 validation, and
  metadata JSON read/write rules.
- `src/moontransfer/files.py`: temporary session directories, destination
  conflict checks, SHA-256 hashing, received-file verification, unique filenames,
  and final file placement.
- `src/moontransfer/progress.py`: parsing `croc` progress output and formatting
  file sizes, transfer rates, elapsed time, and remaining time.
- `src/moontransfer/messages.py`: user-facing status messages derived from
  process output and process results.
- `src/moontransfer/runner.py`: `QProcess` lifecycle, stdout/stderr splitting,
  process termination, and stdin replies to `croc` prompts.
- `src/moontransfer/desktop.py`: opening folders through the platform file
  manager and cleaning the environment used for external desktop commands.
- `tools/build.py`: common PyInstaller build orchestration.
- `tools/fetch_croc.py`: pinned `croc` release selection, download, checksum
  verification, archive extraction, and bundled binary installation.
- `tools/check_latest_croc.py`: compatibility checks against the latest upstream
  `croc` release.
- `scripts/build.sh` and `scripts/build.ps1`: user-facing build wrappers and
  prerequisite checks.
- `MoonTransfer.spec`: PyInstaller packaging configuration.

When changing a runtime module, update or add the matching test file under
`tests/` whenever practical. The test names already mirror most runtime and
maintenance modules.

### Development setup

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

### Python version policy

Python compatibility is declared in two places:

- `pyproject.toml`, through `requires-python`;
- `.python-version`, used by tools such as `uv` to select a compatible runtime.

Keep both files aligned. At the moment MoonTransfer supports Python
`>=3.13,<3.15`, meaning Python 3.13.x and 3.14.x are accepted.

If the supported Python range changes:

1. update `requires-python` in `pyproject.toml`;
2. update `.python-version` with the same range;
3. update the Python instructions in both README files;
4. run `uv lock` if dependency resolution can be affected;
5. run `uv sync --frozen --dev`;
6. run the automatic checks;
7. run a build if the change can affect packaging.

Do not narrow the supported Python range without a concrete reason, such as a
dependency constraint, an unsupported Python release, or a runtime behavior that
cannot be handled cleanly.

### Dependency changes

`uv.lock` is committed intentionally. It makes dependency resolution
reproducible for development, tests, and local builds.

If you change Python dependencies:

1. edit `pyproject.toml`;
2. update `uv.lock` with `uv lock`;
3. run `uv sync --frozen --dev`;
4. run the automatic checks;
5. commit both `pyproject.toml` and `uv.lock`.

Do not edit `uv.lock` manually.

### Development run

Start MoonTransfer from the project root:

```sh
uv run moontransfer
```

Useful references:

- [`croc`](https://github.com/schollz/croc), transfer engine;
- [`uv`](https://docs.astral.sh/uv/), Python environment and dependency
  management;
- [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/), GUI toolkit;
- [PyInstaller](https://pyinstaller.org/en/stable/), bundle creation.

### Automatic tests

Unit tests cover the non-GUI logic split across the runtime modules and
maintenance tools: command construction, transfer output parsing, user-facing
status messages, desktop integration helpers, process-output splitting, pinned
`croc` asset selection, and latest-release check helpers.

They do not exercise real GUI interaction and they do not perform a real file
transfer by default. Use the manual transfer test for that.

Run the unit test suite:

```sh
uv run --frozen python -m unittest discover -s tests
```

Check that the Python modules compile:

```sh
uv run --frozen python -m py_compile src/moontransfer/*.py tools/*.py
```

### Testing expectations by change type

Use the smallest test set that covers the risk of the change, then broaden it
when the behavior crosses module or platform boundaries.

- Documentation-only changes: run `git diff --check`. If the documentation
  describes commands or paths, also verify them against the repository.
- Changes to `croc` arguments, `CROC_SECRET`, command previews, or isolated
  configuration: run `tests/test_croc.py`, `tests/test_check_latest_croc.py`,
  and the full unit test suite.
- Changes to metadata JSON, generated codes, filename validation, hash
  validation, or protocol versioning: run `tests/test_protocol.py` and
  `tests/test_files.py`.
- Changes to destination handling, overwrite/rename behavior, hashing, or final
  file placement: run `tests/test_files.py` and perform a manual receive test.
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
- Changes to the main transfer flow or GUI coordination: run the full unit test
  suite, start MoonTransfer manually, and perform a manual transfer test.

### Manual transfer test

To verify the full flow during development, you can use two MoonTransfer
instances on the same machine:

1. open two MoonTransfer instances;
2. in the first instance, send a small file;
3. copy the displayed code;
4. in the second instance, receive into a different folder;
5. check that the file was created in the destination folder.

This test is useful for development, but it is not the main use case of the
program, which remains transferring between two different computers.

### Before committing

Run these checks before committing:

```sh
uv lock --check
uv run --frozen python -m unittest discover -s tests
uv run --frozen python -m py_compile src/moontransfer/*.py tools/*.py
git diff --check
```

If you touch build scripts, packaging, or `MoonTransfer.spec`, also run the
build script for the platform you changed.

### Maintenance tasks

#### Check the latest croc release

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

The transfer check starts a sender and a receiver with the latest `croc`
binary, transfers a small temporary file, and verifies the received content. It
requires Internet access and a reachable `croc` relay, so it is intentionally
not part of the default check.

If the check passes for a new release, update `[tool.moontransfer.croc]` in
`pyproject.toml` with the new version and official hashes, then run the normal
test suite before committing.

### Architecture notes

- MoonTransfer starts `croc` with `QProcess`, without going through shells such
  as bash, fish, or PowerShell.
- `src/moontransfer/app.py` keeps the application entry point, main window, and
  send/receive tabs. Reusable behavior is split into smaller modules:
  `croc.py` for `croc` command construction, `protocol.py` for the
  MoonTransfer control JSON messages, `files.py` for hashing, temporary
  directories, conflict checks, and final file placement, `progress.py` for
  transfer output parsing, `messages.py` for user-facing status text,
  `desktop.py` for file manager integration, `runner.py` for `QProcess`
  handling, and `widgets.py` for shared Qt widgets.
- The bundled `croc` version is pinned in `pyproject.toml`; supported release
  archives are verified with versioned SHA-256 hashes before extraction.
- When sending, MoonTransfer generates metadata and main file codes itself. The
  visible code is only the metadata code. Transfer codes are passed through
  `CROC_SECRET`, because modern non-classic `croc` does not accept custom send
  codes through `--code` on Unix systems:

```text
CROC_SECRET=<hidden> croc --classic=false --ignore-stdin --disable-clipboard send --no-local <file>
```

`--no-local` avoids `croc`'s local relay, which can make negotiation unstable
in tests with two instances on the same machine.
`--classic=false` keeps MoonTransfer on `croc`'s modern transfer mode even if
the user's global `croc` configuration has remembered classic mode.

After the metadata transfer, the sender starts the main `croc send` process and
waits. The receiver starts the main `croc` process without `--yes`, then
MoonTransfer writes `y` or `n` to that process based on the user's GUI choice.
This uses `croc`'s own accept/reject prompt instead of a separate MoonTransfer
decision transfer. If the receiver rejects the file, the main transfer is
refused and no file content is downloaded.

- When receiving metadata, control files are received into temporary session
  directories first. Transfer codes are passed through `CROC_SECRET`, not as
  positional command-line arguments:

```text
CROC_SECRET=<hidden> croc --classic=false --ignore-stdin --yes --overwrite
```

The main file receive process intentionally keeps stdin open and does not use
`--yes`, so MoonTransfer can answer `croc`'s prompt:

```text
CROC_SECRET=<hidden> croc --classic=false --overwrite
```

Each transfer session also gives `croc` an isolated temporary configuration
directory, so MoonTransfer does not depend on or modify the user's global
`croc` settings.

The command preview shown in the technical details masks internal transfer
codes. The final file is moved to the selected destination only after the
expected size and SHA-256 hash are verified.

- Build reproducibility depends on `uv.lock`, the pinned `croc` version, and
  the versioned SHA-256 hashes in `pyproject.toml`.

### Structure

```text
MoonTransfer/
├─ src/
│  └─ moontransfer/
│     ├─ app.py
│     ├─ croc.py
│     ├─ desktop.py
│     ├─ files.py
│     ├─ messages.py
│     ├─ protocol.py
│     ├─ progress.py
│     ├─ runner.py
│     └─ widgets.py
├─ tools/
│  ├─ build.py
│  ├─ check_latest_croc.py
│  └─ fetch_croc.py
├─ scripts/
│  ├─ build.ps1
│  └─ build.sh
├─ tests/
│  ├─ test_check_latest_croc.py
│  ├─ test_croc.py
│  ├─ test_desktop.py
│  ├─ test_fetch_croc.py
│  ├─ test_files.py
│  ├─ test_messages.py
│  ├─ test_protocol.py
│  ├─ test_progress.py
│  └─ test_runner.py
├─ README.md
├─ README.it.md
├─ LICENSE
├─ MoonTransfer.spec
├─ pyproject.toml
├─ uv.lock
└─ THIRD_PARTY_NOTICES.md
```

### Generated files

These paths are generated locally and should not be committed:

```text
.venv/
.cache/
build/
dist/
third_party/croc/
__pycache__/
```

If one of these paths appears in `git status`, leave it out of the commit.

## Licenses

MoonTransfer is distributed under the GNU General Public License version 3.
See the full license text in [LICENSE](LICENSE).

Third-party components keep their own licenses. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for third-party components,
in particular `croc` and PySide6/Qt for Python.

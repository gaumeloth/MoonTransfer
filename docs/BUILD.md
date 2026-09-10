# Build and run MoonTransfer desktop

[Italiano](BUILD.it.md) | [MoonTransfer](../README.md)

Run commands from the checkout root unless stated otherwise. This guide covers desktop builds; use the [dedicated guide](../android/README.md) for Android.

## Contents

- [Download the source](#download-the-source)
- [Prepare the system](#prepare-the-system)
- [Create the build](#create-the-build)
- [Start MoonTransfer](#start-moontransfer)

## Download the source

Building from source remains useful for contributors, unsupported release
architectures, or anyone who wants to inspect the complete build process.

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
<summary>Linux</summary>

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
<summary>macOS</summary>

From the project folder:

```sh
./scripts/build.sh
```

You can launch the command from fish, bash, or zsh as `./scripts/build.sh`.
Do not run it as `fish scripts/build.sh`.

If the build completes successfully, the application bundle will be:

```text
dist/MoonTransfer.app
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
then PyInstaller using `MoonTransfer.spec`. Before packaging, it writes the
ignored `build/generated/build-info.json` file. A local build receives a
`0.1.0-dev.<commit>` identity; a clean checkout at an exact pre-release tag
receives that tag's version. Release automation passes the version and commit
explicitly so the archive name and the version shown by the application cannot
diverge.

The application icon has a single version-controlled PNG source. Qt loads that
PNG directly at runtime. On Windows and macOS, PyInstaller uses the Pillow
development dependency to convert it to the native application icon during the
build, so separate `.ico` and `.icns` sources do not need to be maintained.

To check the latest upstream `croc` release without changing the build pin:

```sh
uv run --frozen python tools/fetch_croc.py --latest
```

</details>

## Start MoonTransfer

After the build, use the output described for your operating system below. On
Linux and Windows, keep the entire generated folder together: the executable
must remain next to the files and folders generated by PyInstaller. On macOS,
keep the generated application bundle intact.

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

Open `dist/` in Finder and start:

```text
MoonTransfer.app
```

The application is not currently signed or notarized. If macOS blocks its first
start, Control-click `MoonTransfer.app`, choose **Open**, and confirm. Depending
on the macOS version, you can also allow it from **System Settings > Privacy &
Security**.

From the project folder, Finder can also be asked to open the application with:

```sh
open dist/MoonTransfer.app
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

# Third-party notices

MoonTransfer bundles and/or depends on third-party software.

## croc

MoonTransfer uses the `croc` command-line tool as its transfer engine.

Project: <https://github.com/schollz/croc>  
License: MIT License

For desktop, the `croc` binary is downloaded during the build process by `tools/fetch_croc.py`
and bundled into the final application package. The bundled version and the
expected SHA-256 hashes for supported release archives are declared in
`pyproject.toml` under `[tool.moontransfer.croc]`.

Android instead builds the pinned, checksum-verified release source with the
local [python-for-android recipe](android/recipes/README.md). Its MIT license is
included in the APK and in the [bundled license text](android/app/moontransfer_android/licenses/croc.txt).

## PySide6 / Qt for Python

MoonTransfer uses PySide6 for its graphical interface.

Project: <https://doc.qt.io/qtforpython/>  
Package: <https://pypi.org/project/PySide6/>

PySide6 is distributed under the licensing terms provided by Qt/PySide6.
It is used by desktop builds, not by the Android runtime.

## Kivy

The experimental Android client uses Kivy for its graphical interface. Kivy is
not included in MoonTransfer desktop release artifacts.

Project: <https://github.com/kivy/kivy>

License: MIT License

## Lucide

The Android interface uses selected Lucide icons, converted to PNG assets for
Kivy and bundled in the APK.

Project: <https://github.com/lucide-icons/lucide>

License: ISC License, with MIT-licensed Feather-derived icons as documented in
the bundled `android/app/moontransfer_android/assets/icons/LICENSE-lucide.txt`.

## Buildozer / python-for-android

The experimental Android build uses Buildozer and python-for-android as
build-time tooling. Their versions are pinned in the Android-specific project
and Buildozer configuration.

Projects: <https://github.com/kivy/buildozer> and
<https://github.com/kivy/python-for-android>

License: MIT License

## Scope of this document

This overview distinguishes application dependencies from build tools; it is
not an exhaustive inventory of every transitive or native library in a bundle.
When changing packaging, review the actual bundled components and their license
texts, including the Python runtime and native Android dependencies. Preserve
upstream copyright notices; do not translate or replace their license texts.

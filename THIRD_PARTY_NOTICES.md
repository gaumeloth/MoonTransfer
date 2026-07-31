# Third-party notices

MoonTransfer bundles and/or depends on third-party software.

## croc

MoonTransfer uses the `croc` command-line tool as its transfer engine.

Project: <https://github.com/schollz/croc>  
License: MIT License

The `croc` binary is downloaded during the build process by `tools/fetch_croc.py`
and bundled into the final application package. The bundled version and the
expected SHA-256 hashes for supported release archives are declared in
`pyproject.toml` under `[tool.moontransfer.croc]`.

## PySide6 / Qt for Python

MoonTransfer uses PySide6 for its graphical interface.

Project: <https://doc.qt.io/qtforpython/>  
Package: <https://pypi.org/project/PySide6/>

PySide6 is distributed under the licensing terms provided by Qt/PySide6.

## Kivy

The experimental Android client uses Kivy for its graphical interface. Kivy is
not included in MoonTransfer desktop release artifacts.

Project: <https://github.com/kivy/kivy>

License: MIT License

## Buildozer / python-for-android

The experimental Android build uses Buildozer and python-for-android as
build-time tooling. Their versions are pinned in the Android-specific project
and Buildozer configuration.

Projects: <https://github.com/kivy/buildozer> and
<https://github.com/kivy/python-for-android>

License: MIT License

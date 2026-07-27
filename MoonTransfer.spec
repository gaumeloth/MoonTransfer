# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os


# PyInstaller non garantisce __file__ dentro lo spec.
# SPECPATH è la directory del file .spec.
ROOT = Path(SPECPATH).resolve()
SRC = ROOT / "src"
APP_ICON = SRC / "moontransfer" / "assets" / "icons" / "moontransfer-icon.png"

if os.name == "nt":
    CROC_BIN = ROOT / "third_party" / "croc" / "croc.exe"
else:
    CROC_BIN = ROOT / "third_party" / "croc" / "croc"

if not CROC_BIN.exists():
    raise FileNotFoundError(
        f"Binario croc non trovato: {CROC_BIN}\n"
        "Esegui prima: uv run python tools/fetch_croc.py"
    )

if not APP_ICON.exists():
    raise FileNotFoundError(f"Icona dell'applicazione non trovata: {APP_ICON}")


a = Analysis(
    [str(SRC / "moontransfer" / "app.py")],
    pathex=[str(SRC)],
    binaries=[
        (str(CROC_BIN), "."),
    ],
    datas=[
        (str(APP_ICON), "moontransfer/assets/icons"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MoonTransfer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=str(APP_ICON) if os.name == "nt" else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="MoonTransfer",
)

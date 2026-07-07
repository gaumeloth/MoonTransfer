# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

if os.name == "nt":
    CROC_BIN = ROOT / "third_party" / "croc" / "croc.exe"
else:
    CROC_BIN = ROOT / "third_party" / "croc" / "croc"

if not CROC_BIN.exists():
    raise FileNotFoundError(
        f"Binario croc non trovato: {CROC_BIN}\n"
        "Esegui prima: uv run python tools/fetch_croc.py"
    )


a = Analysis(
    [str(SRC / "moontransfer" / "app.py")],
    pathex=[str(SRC)],
    binaries=[
        (str(CROC_BIN), "."),
    ],
    datas=[],
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

# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: KimoTranslate.exe (GUI) + KimoTranslate-Updater.exe.

La GUI es stdlib puro (tkinter+urllib): el bundle no lleva FastAPI/workers.
NO probado en Linux: ejecutar scripts/build_windows_gui.ps1 en Windows.
"""
import os

VERSION = open("build_version.txt", encoding="utf-8").read().strip()

gui_app = Analysis(
    ["gui/tkinter/app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("gui", "gui"),  # vistas/componentes por path (import dinámico) + config/update
        ("build_version.txt", "."),
    ],
    hiddenimports=["customtkinter"],
    excludes=["PIL", "numpy", "httpx", "fastapi", "uvicorn", "pydantic"],
)

updater_app = Analysis(
    ["gui/updater.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    excludes=["PIL", "numpy", "httpx", "fastapi", "uvicorn", "pydantic", "tkinter"],
)

gui_exe = EXE(
    PYZ(gui_app.pure, gui_app.zipped_data),
    gui_app.scripts,
    gui_app.binaries,
    gui_app.zipfiles,
    gui_app.datas,
    name="KimoTranslate",
    debug=False,
    console=False,
    icon="NONE",
)

updater_exe = EXE(
    PYZ(updater_app.pure, updater_app.zipped_data),
    updater_app.scripts,
    updater_app.binaries,
    updater_app.zipfiles,
    updater_app.datas,
    name="KimoTranslate-Updater",
    debug=False,
    console=True,
    icon="NONE",
)

print("KimoTranslate version:", VERSION)

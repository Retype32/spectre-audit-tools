# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build for Spectre — produces a single Spectre.exe on Windows.
# Build it on a Windows PC with build_exe.bat (it installs what's needed).
#
# Put local_settings.json next to Spectre.exe: the app looks for it there.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # Sidebar icons; main_window.py finds them next to its own code
    datas=[('assets/icons', 'assets/icons')],
    # Optional / lazily imported readers that PyInstaller can't always see
    hiddenimports=['xlrd', 'openpyxl', 'reportlab'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Not used by Spectre — keeps the .exe smaller
    excludes=['tkinter', 'matplotlib', 'IPython', 'pytest', 'PyQt5', 'PyQt6', 'PySide2'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Spectre',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX-packed files are often flagged by antivirus
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no black console window behind the app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

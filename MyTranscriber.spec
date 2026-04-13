# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import shutil


project_dir = Path.cwd()
datas = []
binaries = []

for binary_name in ("ffmpeg", "ffprobe"):
    binary_path = shutil.which(binary_name)
    if binary_path:
        binaries.append((binary_path, "."))


a = Analysis(
    ["gui_app.py"],
    pathex=[str(project_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name="MyTranscriber",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MyTranscriber",
)

app = BUNDLE(
    coll,
    name="MyTranscriber.app",
    icon=None,
    bundle_identifier="com.hyeongu.mytranscriber",
    info_plist={
        "CFBundleName": "MyTranscriber",
        "CFBundleDisplayName": "MyTranscriber",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "LSMinimumSystemVersion": "13.0",
    },
)

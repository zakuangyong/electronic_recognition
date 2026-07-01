# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

project_root = Path(SPECPATH).resolve().parent
src_dir = project_root / "src"
web_dist = project_root / "web" / "dist"
sys.path.insert(0, str(src_dir))

datas = []
if web_dist.is_dir():
    datas.append((str(web_dist), "web_dist"))

hiddenimports = [
    "cv2",
    "fitz",
    "multipart.multipart",
    "numpy",
    "openpyxl",
    "PIL.Image",
    "pythoncom",
    "pywintypes",
    "uvicorn.lifespan.on",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "win32com.client",
]

a = Analysis(
    [str(project_root / "packaging" / "production_entry.py")],
    pathex=[str(src_dir), str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "matplotlib",
        "pandas",
        "pytest",
        "scipy",
        "torch",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ElectronicRecognition",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ElectronicRecognition",
)

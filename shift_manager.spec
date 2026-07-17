# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Windows interview / demo EXE
# Build: pyinstaller --noconfirm shift_manager.spec

block_cipher = None

from PyInstaller.utils.hooks import collect_submodules, collect_all

datas = [
    ("templates", "templates"),
    ("static", "static"),
    ("packaging/README_EXE.txt", "."),
]

hiddenimports = [
    "desktop_launcher",
    "main",
    "leave_portal_main",
    "app_paths",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

hiddenimports += collect_submodules("routers")
hiddenimports += collect_submodules("services")
hiddenimports += collect_submodules("schemas")
hiddenimports += collect_submodules("db")
hiddenimports += collect_submodules("data")

for pkg in ("uvicorn", "fastapi", "starlette", "anyio", "jinja2"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        hiddenimports += pkg_hidden
    except Exception:
        pass

a = Analysis(
    ["desktop_launcher.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ShiftManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

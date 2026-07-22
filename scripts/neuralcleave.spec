# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the neuralcleave desktop backend sidecar.
#
# Usage (from the repo root):
#   pip install pyinstaller
#   pyinstaller scripts/neuralcleave.spec
#
# The output single-file executable ends up at:
#   dist/neuralcleave-backend.exe   (Windows)
#   dist/neuralcleave-backend       (macOS / Linux)
#
# The bundle_backend.ps1 script copies it to
#   frontend/src-tauri/binaries/neuralcleave-backend-<target-triple>.exe
# so Tauri can embed it as a sidecar in the NSIS installer.

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # repo root

a = Analysis(
    [str(ROOT / "neuralcleave" / "desktop_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Include the default config template so config_init() works inside
        # the frozen binary without needing the source tree.
        (str(ROOT / "neuralcleave"), "neuralcleave"),
    ],
    hiddenimports=[
        # FastAPI / Starlette internals that PyInstaller misses
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "starlette.routing",
        "starlette.middleware",
        "starlette.middleware.cors",
        # aiosqlite
        "aiosqlite",
        # httpx transports
        "httpx._transports.default",
        "httpx._transports.asgi",
        # Channel adapters (optional — silently skipped if deps not installed)
        "neuralcleave.channels.telegram",
        "neuralcleave.channels.discord",
        "neuralcleave.channels.slack",
        "neuralcleave.channels.whatsapp",
        "neuralcleave.channels.email",
        "neuralcleave.channels.sms",
        "neuralcleave.channels.irc",
        "neuralcleave.channels.matrix",
        "neuralcleave.channels.mattermost",
        "neuralcleave.channels.signal",
        "neuralcleave.channels.teams",
        "neuralcleave.channels.mastodon",
        "neuralcleave.channels.nextcloud",
        "neuralcleave.channels.webhook",
        # Voice (optional)
        "neuralcleave.voice.stt",
        "neuralcleave.voice.tts",
        # Click / Rich
        "click",
        "rich",
        "rich.console",
        "rich.table",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy ML frameworks not needed at runtime
        "torch",
        "tensorflow",
        "matplotlib",
        "PIL",
        "cv2",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="neuralcleave-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # no console window — logs go to stderr captured by Tauri
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "frontend" / "src-tauri" / "icons" / ("icon.ico" if sys.platform == "win32" else "icon.png")),
)

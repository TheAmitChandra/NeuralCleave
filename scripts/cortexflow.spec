# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the CortexFlow-AI desktop backend sidecar.
#
# Usage (from the repo root):
#   pip install pyinstaller
#   pyinstaller scripts/cortexflow.spec
#
# The output single-file executable ends up at:
#   dist/cortexflow-backend.exe   (Windows)
#   dist/cortexflow-backend       (macOS / Linux)
#
# The bundle_backend.ps1 script copies it to
#   frontend/src-tauri/binaries/cortexflow-backend-<target-triple>.exe
# so Tauri can embed it as a sidecar in the NSIS installer.

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # repo root

a = Analysis(
    [str(ROOT / "cortexflow_ai" / "desktop_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Include the default config template so config_init() works inside
        # the frozen binary without needing the source tree.
        (str(ROOT / "cortexflow_ai"), "cortexflow_ai"),
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
        "cortexflow_ai.channels.telegram",
        "cortexflow_ai.channels.discord",
        "cortexflow_ai.channels.slack",
        "cortexflow_ai.channels.whatsapp",
        "cortexflow_ai.channels.email",
        "cortexflow_ai.channels.sms",
        "cortexflow_ai.channels.irc",
        "cortexflow_ai.channels.matrix",
        "cortexflow_ai.channels.mattermost",
        "cortexflow_ai.channels.signal",
        "cortexflow_ai.channels.teams",
        "cortexflow_ai.channels.mastodon",
        "cortexflow_ai.channels.nextcloud",
        "cortexflow_ai.channels.webhook",
        # Voice (optional)
        "cortexflow_ai.voice.stt",
        "cortexflow_ai.voice.tts",
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
    name="cortexflow-backend",
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
    icon=str(ROOT / "frontend" / "public" / "logo.png"),
)

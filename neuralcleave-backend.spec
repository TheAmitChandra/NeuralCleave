# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the NeuralCleave desktop backend sidecar.
#
# Usage:
#   pyinstaller --noconfirm neuralcleave-backend.spec
#
# The output lands in dist/neuralcleave-backend[.exe].
# bundle_backend.ps1 (called by Tauri's beforeBuildCommand) copies it to
# src-tauri/binaries/neuralcleave-backend-<target-triple>[.exe] where Tauri's
# externalBin resolution can pick it up.

import sys
from pathlib import Path

# Repo root is one directory above this spec file.
HERE = Path(SPECPATH)  # noqa: F821 — PyInstaller injects SPECPATH

a = Analysis(
    [str(HERE / "neuralcleave" / "desktop_launcher.py")],
    pathex=[str(HERE)],
    binaries=[],
    datas=[
        # Include default config template so first-run works out of the box.
        (str(HERE / "neuralcleave"), "neuralcleave"),
    ],
    hiddenimports=[
        # Core runtime
        "neuralcleave",
        "neuralcleave.gateway.main",
        "neuralcleave.gateway.routes",
        "neuralcleave.gateway.websocket",
        "neuralcleave.config",
        "neuralcleave.agent.runtime",
        # uvicorn — imported at runtime by gateway.main.run()
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.protocols.websockets.wsproto_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # FastAPI / Starlette internals not always found by static analysis
        "fastapi",
        "starlette.routing",
        "starlette.middleware.cors",
        # Encoding helpers that may not be picked up on Windows
        "encodings",
        "encodings.utf_8",
        "encodings.cp1252",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev/test-only packages — shrink the bundle
        "pytest",
        "ruff",
        "mypy",
        "black",
        "isort",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821 — PyInstaller injects PYZ

exe = EXE(  # noqa: F821 — PyInstaller injects EXE
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
    console=True,       # keep console — Tauri reads our stderr for logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

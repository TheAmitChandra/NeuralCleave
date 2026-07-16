#!/usr/bin/env bash
# Bundle the Python gateway backend into a single Linux binary via PyInstaller.
#
# Output: frontend/src-tauri/binaries/cortexflow-backend-x86_64-unknown-linux-gnu
#
# Requirements:
#   pip install pyinstaller cortexflow-ai  (or editable install from repo root)
#   apt-get install -y binutils  # needed by PyInstaller on Debian/Ubuntu
#
# Usage:
#   bash scripts/bundle_backend_linux.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC="$REPO_ROOT/cortexflow-backend.spec"
DIST="$REPO_ROOT/dist"
DEST="$REPO_ROOT/frontend/src-tauri/binaries"

# Detect architecture for Tauri's triple naming convention
ARCH="$(uname -m)"
if [ "$ARCH" = "aarch64" ]; then
  TRIPLE="aarch64-unknown-linux-gnu"
else
  TRIPLE="x86_64-unknown-linux-gnu"
fi

TARGET="$DEST/cortexflow-backend-$TRIPLE"

echo "[bundle-backend-linux] building for $TRIPLE …"
cd "$REPO_ROOT"
python -m PyInstaller "$SPEC" --noconfirm

mkdir -p "$DEST"
cp "$DIST/cortexflow-backend" "$TARGET"
chmod +x "$TARGET"

echo "[bundle-backend-linux] done → $TARGET"

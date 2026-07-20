#!/usr/bin/env bash
# Bundle the Python gateway backend into a single macOS binary via PyInstaller.
#
# Output: frontend/src-tauri/binaries/neuralcleave-backend-aarch64-apple-darwin
#         (Apple Silicon; Intel machines produce x86_64-apple-darwin)
#
# Requirements:
#   pip install pyinstaller neuralcleave  (or editable install from repo root)
#
# Usage:
#   bash scripts/bundle_backend_mac.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC="$REPO_ROOT/neuralcleave-backend.spec"
DIST="$REPO_ROOT/dist"
DEST="$REPO_ROOT/frontend/src-tauri/binaries"

# Detect architecture for Tauri's triple naming convention
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then
  TRIPLE="aarch64-apple-darwin"
else
  TRIPLE="x86_64-apple-darwin"
fi

TARGET="$DEST/neuralcleave-backend-$TRIPLE"

echo "[bundle-backend-mac] building for $TRIPLE …"
cd "$REPO_ROOT"
python -m PyInstaller "$SPEC" --noconfirm

mkdir -p "$DEST"
cp "$DIST/neuralcleave-backend" "$TARGET"
chmod +x "$TARGET"

echo "[bundle-backend-mac] done → $TARGET"

#!/usr/bin/env bash
# neuralcleave CLI installer for macOS and Linux
# Installs the `neuralcleave` CLI from PyPI into the currently active Python environment.
# Run after installing the desktop app if you want `neuralcleave` available in your terminal.

set -euo pipefail

echo "[neuralcleave] Installing neuralcleave CLI from PyPI..."
python3 -m pip install --upgrade neuralcleave

echo ""
echo "[neuralcleave] Installation complete."
echo "Run 'neuralcleave --help' to get started."

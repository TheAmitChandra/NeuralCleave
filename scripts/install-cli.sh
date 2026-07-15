#!/usr/bin/env bash
# CortexFlow-AI CLI installer for macOS and Linux
# Installs the `cortex` CLI from PyPI into the currently active Python environment.
# Run after installing the desktop app if you want `cortex` available in your terminal.

set -euo pipefail

echo "[CortexFlow-AI] Installing cortexflow-ai CLI from PyPI..."
python3 -m pip install --upgrade cortexflow-ai

echo ""
echo "[CortexFlow-AI] Installation complete."
echo "Run 'cortex --help' to get started."

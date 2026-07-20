#!/usr/bin/env bash
# NeuralCleave one-line installer — Linux / macOS
#
# Usage:
#   curl -fsSL https://NeuralCleave.ai/install.sh | bash
#
# What it does:
#   1. Detects a Python 3.12+ interpreter.
#   2. Installs neuralcleave from PyPI via pip.
#   3. Runs `cortex init --non-interactive` to write default config.
#   4. Prints next steps.

set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

_ok()   { printf "  ${GREEN}✓${NC} %s\n" "$*"; }
_info() { printf "  ${CYAN}→${NC} %s\n" "$*"; }
_warn() { printf "  \033[1;33m!${NC} %s\n" "$*"; }
_err()  { printf "  ${RED}✗${NC} %s\n" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

printf "\n  ${BOLD}NeuralCleave — One-line Installer${NC}\n"
printf "  Personal AI Assistant Gateway\n\n"

# ---------------------------------------------------------------------------
# 1. Detect Python 3.12+
# ---------------------------------------------------------------------------

PYTHON=""
for cmd in python3.14 python3.13 python3.12 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        _major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
        _minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
        if [ "$_major" -ge 3 ] && [ "$_minor" -ge 12 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    _err "Python 3.12+ is required. Install from https://www.python.org/downloads/"
fi

PY_VER=$("$PYTHON" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}')")
_ok "Python ${PY_VER} found (${PYTHON})"

# ---------------------------------------------------------------------------
# 2. Install neuralcleave
# ---------------------------------------------------------------------------

_info "Installing neuralcleave from PyPI…"

if ! "$PYTHON" -m pip install --upgrade --quiet neuralcleave 2>&1; then
    # Try --user if system pip fails
    _warn "System pip failed, retrying with --user…"
    "$PYTHON" -m pip install --upgrade --quiet --user neuralcleave \
        || _err "pip install failed. Try manually: pip install neuralcleave"
fi

_ok "neuralcleave installed"

# ---------------------------------------------------------------------------
# 3. Resolve the 'cortex' command
# ---------------------------------------------------------------------------

# Give pip a moment, then refresh PATH
hash -r 2>/dev/null || true

CORTEX_CMD=""
if command -v cortex &>/dev/null; then
    CORTEX_CMD="cortex"
else
    # Common --user install locations
    for loc in \
        "${HOME}/.local/bin/cortex" \
        "${HOME}/Library/Python/3.12/bin/cortex" \
        "${HOME}/Library/Python/3.13/bin/cortex"
    do
        if [ -x "$loc" ]; then
            CORTEX_CMD="$loc"
            break
        fi
    done
fi

# ---------------------------------------------------------------------------
# 4. First-time setup (non-interactive)
# ---------------------------------------------------------------------------

_info "Running first-time setup…"
if [ -n "$CORTEX_CMD" ]; then
    "$CORTEX_CMD" init --non-interactive || true
else
    "$PYTHON" -m neuralcleave.cli init --non-interactive || true
fi

# ---------------------------------------------------------------------------
# 5. Done
# ---------------------------------------------------------------------------

printf "\n  ${BOLD}${GREEN}NeuralCleave is ready!${NC}\n\n"
printf "  Quick start:\n"
printf "    export ANTHROPIC_API_KEY=sk-ant-…\n"
printf "    cortex start\n\n"
printf "  Customise your config:  cortex init --force\n"
printf "  Open the web UI:        cortex open\n"
printf "  Full reference:         cortex --help\n"

# Warn if cortex is not on PATH yet
if ! command -v cortex &>/dev/null; then
    printf "\n  ${CYAN}Note:${NC} 'cortex' is not on your PATH yet. Add it:\n"
    printf "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc\n"
    printf "    source ~/.bashrc\n"
fi

printf "\n"

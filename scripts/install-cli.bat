@echo off
:: CortexFlow-AI CLI installer for Windows
:: Installs the `cortex` CLI from PyPI into the currently active Python environment.
:: Run after installing the desktop .exe if you want `cortex` available in CMD/PowerShell.

echo [CortexFlow-AI] Installing cortexflow-ai CLI from PyPI...
python -m pip install --upgrade cortexflow-ai

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: pip install failed. Make sure Python is installed and on your PATH.
    exit /b 1
)

echo.
echo [CortexFlow-AI] Installation complete.
echo Run `cortex --help` to get started.

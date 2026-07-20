@echo off
:: neuralcleave CLI installer for Windows
:: Installs the `cortex` CLI from PyPI into the currently active Python environment.
:: Run after installing the desktop .exe if you want `cortex` available in CMD/PowerShell.

echo [neuralcleave] Installing neuralcleave CLI from PyPI...
python -m pip install --upgrade neuralcleave

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: pip install failed. Make sure Python is installed and on your PATH.
    exit /b 1
)

echo.
echo [neuralcleave] Installation complete.
echo Run `cortex --help` to get started.

#Requires -Version 5.1
<#
.SYNOPSIS
    CortexFlow one-line Windows installer.

.DESCRIPTION
    1. Detects Python 3.12+ (tries 'py', 'python3', 'python').
    2. Installs cortexflow-ai from PyPI via pip.
    3. Runs `cortex init --non-interactive` to write default config.
    4. Prints next steps.

.EXAMPLE
    # Paste into an elevated PowerShell prompt:
    iwr -useb https://cortexflow.ai/install.ps1 | iex

.EXAMPLE
    # Or download and inspect first:
    Invoke-WebRequest https://cortexflow.ai/install.ps1 -OutFile install.ps1
    notepad install.ps1
    .\install.ps1
#>

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Ok   ($msg) { Write-Host "  [OK] $msg"  -ForegroundColor Green }
function Write-Info ($msg) { Write-Host "  --> $msg"   -ForegroundColor Cyan }
function Write-Warn ($msg) { Write-Host "  [!] $msg"   -ForegroundColor Yellow }
function Write-Fail ($msg) { Write-Host "  [X] $msg"   -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "  CortexFlow - One-line Installer (Windows)" -ForegroundColor White
Write-Host "  Personal AI Assistant Gateway"
Write-Host ""

# ---------------------------------------------------------------------------
# 1. Detect Python 3.12+
# ---------------------------------------------------------------------------

$PythonCmd = $null
$PythonVer = $null

foreach ($cmd in @("py", "python3", "python")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { continue }
    try {
        $major = [int](& $cmd -c "import sys; print(sys.version_info.major)")
        $minor = [int](& $cmd -c "import sys; print(sys.version_info.minor)")
        if ($major -ge 3 -and $minor -ge 12) {
            $PythonVer = & $cmd -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}')"
            $PythonCmd = $cmd
            break
        }
    } catch { continue }
}

if (-not $PythonCmd) {
    Write-Fail "Python 3.12+ is required. Download from: https://www.python.org/downloads/windows/"
}

Write-Ok "Python $PythonVer found ($PythonCmd)"

# ---------------------------------------------------------------------------
# 2. Install cortexflow-ai
# ---------------------------------------------------------------------------

Write-Info "Installing cortexflow-ai from PyPI..."
& $PythonCmd -m pip install --upgrade --quiet cortexflow-ai
if ($LASTEXITCODE -ne 0) {
    Write-Warn "System pip failed, retrying with --user..."
    & $PythonCmd -m pip install --upgrade --quiet --user cortexflow-ai
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "pip install failed. Try manually: pip install cortexflow-ai"
    }
}
Write-Ok "cortexflow-ai installed"

# ---------------------------------------------------------------------------
# 3. Resolve the 'cortex' command
# ---------------------------------------------------------------------------

$CortexExe  = $null
$CortexArgs = @()

$found = Get-Command cortex -ErrorAction SilentlyContinue
if ($found) {
    $CortexExe = "cortex"
} else {
    # pip Scripts dir for the detected Python
    try {
        $scripts = & $PythonCmd -c "import sysconfig; print(sysconfig.get_path('scripts'))"
        $candidate = Join-Path $scripts "cortex.exe"
        if (Test-Path $candidate) {
            $CortexExe = $candidate
        }
    } catch {}

    if (-not $CortexExe) {
        $CortexExe  = $PythonCmd
        $CortexArgs = @("-m", "cortexflow_ai.cli")
    }
}

# ---------------------------------------------------------------------------
# 4. First-time setup (non-interactive)
# ---------------------------------------------------------------------------

Write-Info "Running first-time setup..."
try {
    & $CortexExe @CortexArgs init --non-interactive
} catch {
    Write-Warn "Setup skipped ($($_.Exception.Message)). Run 'cortex init' to configure manually."
}

# ---------------------------------------------------------------------------
# 5. Done
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "  CortexFlow is ready!" -ForegroundColor Green
Write-Host ""
Write-Host "  Quick start:"
Write-Host "    `$env:ANTHROPIC_API_KEY = 'sk-ant-...'"
Write-Host "    cortex start"
Write-Host ""
Write-Host "  Customise your config:  cortex init --force"
Write-Host "  Open the web UI:        cortex open"
Write-Host "  Full reference:         cortex --help"
Write-Host ""

<#
.SYNOPSIS
    Packages the NeuralCleave Python backend as a standalone sidecar binary
    for Tauri to bundle inside the desktop installer.

.DESCRIPTION
    This script is called by Tauri's beforeBuildCommand (tauri.conf.json).
    It:
      1. Verifies Python and pip are available.
      2. Installs PyInstaller if not already present.
      3. Detects the Rust target triple (used by Tauri to locate the binary).
      4. Runs PyInstaller on the NeuralCleave-desktop entry point with the
         neuralcleave-backend.spec file.
      5. Copies the resulting executable into
         src-tauri/binaries/neuralcleave-backend-<triple>[.exe]
         where Tauri's `externalBin` resolution can find it.

.PARAMETER PythonExe
    Path to the Python interpreter to use.  Defaults to whatever `python`
    resolves to on PATH (or `python3` on non-Windows).

.PARAMETER TargetTriple
    Override the Rust target triple.  If omitted the script calls
    `rustup show active-toolchain` to detect it automatically.

.PARAMETER SkipInstall
    Skip the `pip install pyinstaller NeuralCleave` step.  Useful in CI
    environments where the package is already installed.

.EXAMPLE
    # Standard build (called automatically by `npm run tauri build`)
    pwsh -File scripts\bundle_backend.ps1

.EXAMPLE
    # CI with pre-installed deps, explicit triple
    pwsh -File scripts\bundle_backend.ps1 -SkipInstall -TargetTriple x86_64-pc-windows-msvc
#>

param(
    [string]$PythonExe    = "",
    [string]$TargetTriple = "",
    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Helpers ────────────────────────────────────────────────────────────────────

function Write-Step([string]$msg) {
    Write-Host "`n==> $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "    [OK] $msg" -ForegroundColor Green
}

function Write-Fail([string]$msg) {
    Write-Host "    [FAIL] $msg" -ForegroundColor Red
    exit 1
}

# ── Resolve paths ──────────────────────────────────────────────────────────────

# This script lives in frontend/scripts/; the Tauri project root is one level up.
$ScriptDir   = $PSScriptRoot
$TauriRoot   = Split-Path $ScriptDir -Parent  # frontend/
$RepoRoot    = Split-Path $TauriRoot -Parent   # repo root
$BinariesDir = Join-Path $TauriRoot "src-tauri\binaries"
$SpecFile    = Join-Path $RepoRoot "neuralcleave-backend.spec"
$DistDir     = Join-Path $RepoRoot "dist"

# ── Python interpreter ─────────────────────────────────────────────────────────

Write-Step "Locating Python interpreter"

if (-not $PythonExe) {
    $candidates = @("python", "python3", "py")
    foreach ($c in $candidates) {
        try {
            $null = & $c --version 2>&1
            $PythonExe = $c
            break
        } catch {}
    }
}

if (-not $PythonExe) {
    Write-Fail "Could not find a Python interpreter on PATH. Install Python 3.11+ and retry."
}

$pyVersion = & $PythonExe --version 2>&1
Write-OK "Using $PythonExe ($pyVersion)"

# ── Install dependencies ───────────────────────────────────────────────────────

if (-not $SkipInstall) {
    Write-Step "Installing PyInstaller and NeuralCleave"
    & $PythonExe -m pip install --quiet pyinstaller NeuralCleave
    if ($LASTEXITCODE -ne 0) { Write-Fail "pip install failed" }
    Write-OK "Dependencies installed"
}

# ── Detect Rust target triple ──────────────────────────────────────────────────

Write-Step "Detecting Rust target triple"

if (-not $TargetTriple) {
    try {
        # `rustup show active-toolchain` → e.g. "stable-x86_64-pc-windows-msvc (default)"
        $rustupOut  = & rustup show active-toolchain 2>&1 | Select-Object -First 1
        if ($rustupOut -match "stable-(\S+)") {
            $TargetTriple = $Matches[1]
        }
    } catch {}
}

if (-not $TargetTriple) {
    # Fallback: derive from the OS at runtime
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        $arch = if ([System.Environment]::Is64BitOperatingSystem) { "x86_64" } else { "i686" }
        $TargetTriple = "$arch-pc-windows-msvc"
    } elseif ($IsMacOS) {
        $arch = (uname -m).Trim()
        $TargetTriple = "$arch-apple-darwin"
    } else {
        $arch = (uname -m).Trim()
        $TargetTriple = "$arch-unknown-linux-gnu"
    }
}

Write-OK "Target triple: $TargetTriple"

# ── Run PyInstaller ────────────────────────────────────────────────────────────

Write-Step "Running PyInstaller"

if (Test-Path $SpecFile) {
    Write-OK "Using spec file: $SpecFile"
    & $PythonExe -m PyInstaller --noconfirm --distpath $DistDir $SpecFile
} else {
    Write-OK "No spec file found — building from entry point"
    & $PythonExe -m PyInstaller `
        --noconfirm `
        --onefile `
        --name "neuralcleave-backend" `
        --distpath $DistDir `
        --hidden-import "neuralcleave" `
        --hidden-import "neuralcleave.gateway.main" `
        --hidden-import "neuralcleave.config" `
        --hidden-import "uvicorn" `
        --hidden-import "uvicorn.logging" `
        --hidden-import "uvicorn.loops" `
        --hidden-import "uvicorn.loops.asyncio" `
        --hidden-import "uvicorn.protocols" `
        --hidden-import "uvicorn.protocols.http" `
        --hidden-import "uvicorn.protocols.http.auto" `
        --hidden-import "uvicorn.protocols.websockets" `
        --hidden-import "uvicorn.protocols.websockets.auto" `
        --hidden-import "uvicorn.lifespan" `
        --hidden-import "uvicorn.lifespan.on" `
        --collect-all "neuralcleave" `
        ($RepoRoot + "\neuralcleave\desktop_launcher.py")
}

if ($LASTEXITCODE -ne 0) { Write-Fail "PyInstaller build failed" }
Write-OK "PyInstaller build succeeded"

# ── Copy to Tauri binaries dir ─────────────────────────────────────────────────

Write-Step "Copying binary to src-tauri/binaries/"

# Tauri requires: binaries/neuralcleave-backend-<triple> (no extension on non-Windows,
# .exe suffix is added automatically by Tauri on Windows).
$ext        = if ($TargetTriple -like "*windows*") { ".exe" } else { "" }
$srcName    = "neuralcleave-backend$ext"
$dstName    = "neuralcleave-backend-$TargetTriple$ext"

$srcPath    = Join-Path $DistDir $srcName
$dstPath    = Join-Path $BinariesDir $dstName

if (-not (Test-Path $srcPath)) {
    Write-Fail "Expected binary not found at: $srcPath"
}

if (-not (Test-Path $BinariesDir)) {
    New-Item -ItemType Directory -Force -Path $BinariesDir | Out-Null
}

Copy-Item -Force $srcPath $dstPath
Write-OK "Copied $srcName → src-tauri/binaries/$dstName"

# ── Summary ────────────────────────────────────────────────────────────────────

Write-Step "Done"
Write-Host "  Binary : $dstPath" -ForegroundColor White
Write-Host "  Triple : $TargetTriple" -ForegroundColor White
Write-Host ""
Write-Host "Tauri can now bundle neuralcleave-backend as a sidecar." -ForegroundColor Green

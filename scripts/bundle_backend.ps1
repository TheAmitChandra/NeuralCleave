<#
.SYNOPSIS
    Build the neuralcleave Python backend into a single bundled .exe and
    install it where Tauri expects it as a sidecar binary.

.DESCRIPTION
    1. Verifies PyInstaller is available (pip install pyinstaller if not).
    2. Runs PyInstaller with scripts/neuralcleave.spec from the repo root.
    3. Copies dist/neuralcleave-backend.exe ->
           frontend/src-tauri/binaries/neuralcleave-backend-x86_64-pc-windows-msvc.exe
       so the Tauri bundler picks it up as a named sidecar.

.USAGE
    From the repo root in PowerShell:
        .\scripts\bundle_backend.ps1

    Or as part of the Tauri build pipeline:
        tauri.conf.json "beforeBuildCommand" calls this automatically.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot  = Split-Path $PSScriptRoot -Parent
$SpecFile  = Join-Path $RepoRoot "scripts\neuralcleave.spec"
$DistExe   = Join-Path $RepoRoot "dist\neuralcleave-backend.exe"
$BinDir    = Join-Path $RepoRoot "frontend\src-tauri\binaries"
$TargetExe = Join-Path $BinDir "neuralcleave-backend-x86_64-pc-windows-msvc.exe"

Write-Host "==> NeuralCleave backend bundler" -ForegroundColor Cyan

# ── 1. Ensure PyInstaller is available ──────────────────────────────────────
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
    pip install pyinstaller --quiet
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }
}

# ── 2. Run PyInstaller ───────────────────────────────────────────────────────
Write-Host "Building backend executable with PyInstaller..." -ForegroundColor Yellow
Push-Location $RepoRoot
try {
    pyinstaller $SpecFile --distpath dist --workpath dist\_pyinstaller_work --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
} finally {
    Pop-Location
}

if (-not (Test-Path $DistExe)) {
    throw "Expected output not found: $DistExe"
}

# ── 3. Copy to Tauri binaries directory ─────────────────────────────────────
if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir | Out-Null
}

Copy-Item -Path $DistExe -Destination $TargetExe -Force
Write-Host "Sidecar installed -> $TargetExe" -ForegroundColor Green

$SizeMB = [math]::Round((Get-Item $TargetExe).Length / 1MB, 1)
Write-Host "Bundle size: ${SizeMB} MB" -ForegroundColor Cyan
Write-Host "Done. Run 'npm run tauri build' to build the full installer." -ForegroundColor Green

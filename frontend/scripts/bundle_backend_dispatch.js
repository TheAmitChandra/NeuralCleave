#!/usr/bin/env node
/**
 * Cross-platform dispatcher for the Python backend bundling step.
 *
 * Called by `npm run bundle-backend` (which Tauri runs as part of
 * beforeBuildCommand before every build). Picks the right script for the
 * current OS and runs it synchronously.
 *
 * Skip behaviour: if the target binary already exists AND the env var
 * CORTEXFLOW_SKIP_BUNDLE is set (CI sets this after running the bundle step
 * separately), this script exits 0 without rebuilding — avoids running
 * PyInstaller twice in CI.
 *
 * Platform scripts live in the repo root scripts/ directory:
 *   Windows → scripts/bundle_backend.ps1
 *   macOS   → scripts/bundle_backend_mac.sh
 *   Linux   → scripts/bundle_backend_linux.sh
 */

const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const repoRoot = path.resolve(__dirname, "..", "..");
const binDir = path.join(repoRoot, "frontend", "src-tauri", "binaries");

// Compute the expected binary name for the current platform+arch
function expectedBinaryName() {
  const arch = os.arch() === "arm64" ? "aarch64" : "x86_64";
  if (process.platform === "win32") {
    return `cortexflow-backend-${arch}-pc-windows-msvc.exe`;
  }
  if (process.platform === "darwin") {
    return `cortexflow-backend-${arch}-apple-darwin`;
  }
  return `cortexflow-backend-${arch}-unknown-linux-gnu`;
}

const targetBinary = path.join(binDir, expectedBinaryName());

if (process.env.CORTEXFLOW_SKIP_BUNDLE === "1" && fs.existsSync(targetBinary)) {
  console.log(`[bundle-backend] skipping — binary already exists at ${targetBinary}`);
  process.exit(0);
}

let cmd;
if (process.platform === "win32") {
  const ps1 = path.join(repoRoot, "scripts", "bundle_backend.ps1");
  cmd = `powershell -ExecutionPolicy Bypass -File "${ps1}"`;
} else if (process.platform === "darwin") {
  const sh = path.join(repoRoot, "scripts", "bundle_backend_mac.sh");
  cmd = `bash "${sh}"`;
} else {
  const sh = path.join(repoRoot, "scripts", "bundle_backend_linux.sh");
  cmd = `bash "${sh}"`;
}

console.log(`[bundle-backend] ${cmd}`);
execSync(cmd, { stdio: "inherit" });

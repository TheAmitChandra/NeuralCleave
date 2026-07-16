#!/usr/bin/env node
/**
 * Cross-platform dispatcher for the Python backend bundling step.
 *
 * Called by `npm run bundle-backend` (which Tauri runs before every build).
 * Picks the right script for the current OS and runs it synchronously so
 * Tauri's beforeBuildCommand waits for the result before continuing.
 *
 * Platform scripts live in the repo root scripts/ directory:
 *   Windows → scripts/bundle_backend.ps1
 *   macOS   → scripts/bundle_backend_mac.sh
 *   Linux   → scripts/bundle_backend_linux.sh
 */

const { execSync } = require("child_process");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..", "..");

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

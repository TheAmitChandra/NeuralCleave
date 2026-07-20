# Desktop App Bug Report — 2026-06-30

Produced after dogfooding the real Windows installer end-to-end and a
follow-up deep analysis session. Three bugs were fixed and released, but two
issues persisted and are documented here with confirmed root causes.

---

## Confirmed Root Causes (post-release investigation)

### Bug 1: "Connecting…" never resolves — ROOT CAUSE CONFIRMED

**Short answer:** The user's `test-venv` has `neuralcleave` **2.0.2** installed,
not 2.0.4. Confirmed by running `pip show neuralcleave` directly against
`C:\Amit-Projects\AI-Projects\CortextFlow-AI-Testing\test-venv`:

```
Name: neuralcleave
Version: 2.0.2
Location: C:\...\CortextFlow-AI-Testing\test-venv\Lib\site-packages
```

The CORS fix (adding Tauri webview origins to `allow_origins`) was released in
2.0.4. Running `cortex start` from a 2.0.2 install means the gateway in use
has only `localhost:3000` and `127.0.0.1:3000` in its CORS allowlist. The
desktop app's WebView2 sends requests from `https://tauri.localhost` — which
is not allowed. The gateway processes every request and logs `200 OK`, but the
browser discards the response silently (CORS policy). JS sees an error →
`isError: true` → "Connecting…" forever.

**The fix is not a code change — it is a gateway upgrade in the test-venv:**
```
pip install --upgrade neuralcleave
```
Run this in the `CortextFlow-AI-Testing` environment before restarting
`cortex start`.

**Note on the misleading false positive:** Running the test-venv's Python
binary with `python -c "import neuralcleave; print(__version__)"` while
`cwd` is the dev repo reported `2.0.4` — Python adds the current directory to
`sys.path` in `-c` mode, so it found the dev repo's source instead of the
venv's site-packages. Only `pip show neuralcleave` gives the true installed
version.

**Secondary concern (MEDIUM CONFIDENCE, still unverified):** Even after
upgrading the gateway, the assumed CORS origin strings (`https://tauri.localhost`
on Windows, `tauri://localhost` on macOS/Linux) are based on Tauri 2.x
documentation, not captured from actual network traffic. To verify conclusively:
add a one-line debug log to `create_app()` printing the `Origin` header of each
incoming request, start the gateway, open the desktop app, and read the log.
The strings are correct per Tauri's docs for WebView2 static-file serving via
`SetVirtualHostNameToFolderMapping`, but this has never been empirically
confirmed against this specific build.

---

### Bug 2: App icon still shows old placeholder — ROOT CAUSE CONFIRMED

**Short answer:** Windows icon cache, not a code bug.

The new icons ARE in the v2.0.4 binary:
- Icons regenerated via `tauri icon docs-site/assets/logo.png` and committed in
  `8936221` (merged as `06fa390`)
- The v2.0.4 release tag was created after that commit — CI built from the
  correct source and bundled the new `.ico`

**Why the old icon still shows:** Windows caches `.exe` icons in
`IconCache.db`. After reinstalling over a previous version, the taskbar,
desktop shortcut, and file explorer all show the stale cached image until the
cache is explicitly cleared.

**How to fix (two options):**

Option A — Clear icon cache manually (no restart required):
1. Open Task Manager → File → Run new task → `ie4uinit.exe -show`
2. OR run in an admin Command Prompt:
   ```
   ie4uinit.exe -show
   ```

Option B — Full restart:
Simply restart Windows. Icon cache rebuilds on next login.

**Taskbar pin note:** If neuralcleave is **pinned to the taskbar**, the
pinned shortcut stores its icon separately from the installed binary. Even
after clearing the cache, the pinned icon may stay wrong. Fix: right-click the
pinned item → Unpin from taskbar, then relaunch the app and pin it again.

---

## Bugs Fixed This Session (already released in 2.0.3 / 2.0.4)

### Fix 1: Crash on relaunch after closing to tray (v2.0.3)

- Closing the window hides it (intentional tray behavior), but with no
  single-instance guard, relaunching the `.exe` started a second OS process.
  That process tried to register `Ctrl+Shift+Space` — already held by the
  first instance — failed with an OS error, and `.expect()` panicked.
- Fixed with `tauri-plugin-single-instance`. A second launch now focuses
  the existing window instead.
- Commit: `6a4e034`

### Fix 2: CORS — gateway allowed wrong origins (v2.0.4)

- `CORSMiddleware` only allowed `localhost:3000` / `127.0.0.1:3000` (the
  Next.js dev server). The packaged WebView2 origin was never in the list.
- Added `https://tauri.localhost` and `tauri://localhost`.
- Commit: `1e11890`

### Fix 3: Placeholder branding (v2.0.4)

- Tauri app icon was the default scaffold placeholder (teal/yellow figure-8).
- Sidebar brand mark was a generic `lucide-react` `Zap` icon.
- Web dashboard favicon was Next.js's default triangle.
- All replaced using `docs-site/assets/logo.png` as the source.
- Commit: `8936221`

### Fix 4: deploy-pages race with build-tauri (CI only, no version bump)

- Both workflows fired from `release: published` simultaneously. Pages
  (~2 min) always finished before Tauri builds (~14 min), downloaded no
  installers, and deployed 404 links.
- Fixed by switching the release path from `release: published` to
  `workflow_run: [Build Tauri Installers]: completed`.
- Commit: `a9c1ba8`

---

## What to test manually (cannot be verified from code alone)

- [ ] After `pip install --upgrade neuralcleave` in test-venv: confirm
      Topbar shows "Gateway online" instead of "Connecting…"
- [ ] After clearing icon cache or restarting: confirm taskbar shows the
      real NeuralCleave logo
- [ ] Autostart toggle in Settings actually creates/removes the Windows
      registry entry
- [ ] Native notification appears in Windows Action Center when a reply
      arrives while the window is unfocused
- [ ] Global hotkey `Ctrl+Shift+Space` summons the window from a fully
      backgrounded state (not just from behind another window)
- [ ] Tray tooltip updates with unread count when a channel receives a message

---

## Lessons / process failures this session

1. Never confirmed which gateway version was running before diagnosing
   "Connecting…". `cortex --version` in the test-venv would have resolved
   this in 5 seconds.
2. Released the CORS fix (v2.0.4) without verifying the CORS origin strings
   against real captured network traffic from the packaged app.
3. Released 4 versions in rapid succession (2.0.1 → 2.0.4) with each patch
   fixing something that should have been caught before the previous release.
   The correct sequence was: verify locally → release once.

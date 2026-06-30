# Desktop App Bug Report — 2026-06-30

Found while dogfooding the v2.0.2 Windows installer end-to-end for the first
time (install → run → close → reopen → connect to a real gateway). All three
bugs below share the same root cause class: each one only manifests in a
**packaged build talking to a real gateway** — none of them are reachable
from `cargo check`, `vitest`, or `pytest` alone, which is why they shipped
in 2.0.2 despite 1218+ passing tests.

## Fixed

### 1. Crash on relaunch after closing to tray

- **Symptom**: install the app, close the window once, relaunch the `.exe`
  — crashes immediately, no window appears.
- **Root cause**: closing the window hides it instead of quitting (intentional
  — that's how the tray icon + global hotkey stay alive). With no
  single-instance guard, relaunching spins up a second OS process. Its
  `setup()` tries to register the global hotkey `Ctrl+Shift+Space` via
  `app.global_shortcut().register(summon)?`, but the OS already has that
  hotkey bound to the first (still-running) instance. The `?` propagates the
  `Err`, and `.run(...).expect(...)` panics on it.
- **Fix**: `tauri-plugin-single-instance`, registered first in the builder
  chain. A second launch now gets forwarded to the first instance, which just
  focuses its window — the second process exits before ever reaching the
  hotkey registration.
- **Commit**: `6a4e034` (merged `753bfb1`), shipped in v2.0.3.

### 2. UI stuck on "Connecting…" forever despite a healthy gateway

- **Symptom**: `cortex start` running and logging `200 OK` on every request
  plus a successful WebSocket `connection open` — but the desktop app's
  Topbar never leaves "Connecting…".
- **Root cause**: `create_app()`'s `CORSMiddleware` only allowed the Next.js
  dev-server origins (`localhost:3000` / `127.0.0.1:3000`). The packaged
  app's webview loads the bundled frontend from `https://tauri.localhost`
  (Windows, via WebView2's virtual host) or `tauri://localhost`
  (macOS/Linux) — neither was in `allow_origins`. The browser silently drops
  the response on the JS side when the origin isn't allowed, even though the
  gateway itself processes and logs the request as 200 — so the failure is
  completely invisible in the backend logs.
- **Fix**: added both Tauri origins to `allow_origins`, with regression tests
  asserting the `access-control-allow-origin` header for both the new
  origins and the existing dev-server origin.
- **Commit**: `1e11890` (merged `ea3dbc8`).
- **Note**: this is a REST-only fix. The WebSocket handler
  (`cortexflow_ai/gateway/websocket.py`) has no `Origin` check at all, so it
  was never affected — confirmed by the user's own log showing
  `"WebSocket /ws" [accepted]` and `connection open` succeeding even before
  this fix.

### 3. Placeholder branding never replaced

- **Symptom**: the Tauri app icon (taskbar, title bar, installer, Windows
  Store tiles), the in-app sidebar logo, and the web dashboard's browser-tab
  favicon were all still scaffold placeholders — a generic teal/yellow
  figure-8 (Tauri's default), a `lucide-react` `Zap` icon, and Next.js's
  default triangle-in-circle, respectively. None of them were ever the real
  CortexFlow mark.
- **Fix**: regenerated the full Tauri icon set (ICO, ICNS, all PNG sizes,
  Windows Store tiles, Android/iOS mipmaps) from `docs-site/assets/logo.png`
  via `tauri icon` (the CLI's own tool — not hand-resized). Replaced the
  sidebar's `Zap` placeholder with the same logo at 256×256 (down from the
  1254×1254 source — 53KB is plenty for a 28px icon, the original was
  1.1MB). Regenerated `favicon.ico` the same way.
- **Commit**: `8936221` (merged `06fa390`).
- **Verified**: rendered via a real `npm run dev` + Playwright screenshot —
  logo displays correctly in the sidebar, no console errors.

## Audited, no bug found

Code-level review of the remaining desktop-specific integration points
(triggered by the same incident — if three things were broken, worth
checking the rest before calling it done):

| Area | File | Finding |
|---|---|---|
| Native notifications | `frontend/src/lib/notifications.ts` | Correctly gated on `isTauri()`, requests permission via the plugin before sending. |
| Tray unread badge | `frontend/src/lib/trayBadge.ts` → `set_unread_badge` (Rust) | Wired end-to-end: `layout.tsx` sums unread counts from `/channels` and calls it on every poll. |
| Notification trigger | `frontend/src/app/(dashboard)/layout.tsx` | Listens for `message_done` (not the dead `message` type), checks `document.hasFocus()` before notifying — matches the current streaming protocol. |
| Autostart toggle | `frontend/src/app/(dashboard)/settings/page.tsx` | Correctly wired to `@tauri-apps/plugin-autostart`, gated to Tauri-only, reflects actual OS state on load. |
| Gateway base URL | `frontend/src/lib/api.ts` | Hardcoded to `http://localhost:7432` by default, matching the documented gateway port — not the source of bug #2. |

This was a **code-level audit, not hands-on GUI testing** — I can't drive a
Windows GUI session directly. Toggling autostart, confirming a real OS
notification pops up, and watching the tray badge update live all still
need a human to actually click through them once on the v2.0.3 build.

## Still open / needs manual verification

- [ ] Autostart toggle actually creates/removes the Windows registry entry
      (or LaunchAgent on macOS) — code looks correct, never click-tested.
- [ ] Tray icon's unread badge tooltip updates live when a channel receives
      a message while the window is unfocused.
- [ ] Native notification actually appears in the Windows Action Center
      (not just that `sendNotification()` is called without throwing).
- [ ] Global hotkey `Ctrl+Shift+Space` still resolves correctly now that
      single-instance forwarding is in the mix — confirm it summons the
      window from a fully backgrounded (not just hidden) state.

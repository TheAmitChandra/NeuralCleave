"""FastAPI routers for the PWA mobile companion interface.

Two routers are exported:
  pwa_router  — PWA shell routes (/, /app, /manifest.json, /sw.js, icons)
  push_router — Web Push subscription CRUD under /api/v1/push/

The HTML app shell embeds a Service Worker registration and connects
via the WebSocket protocol at /ws.  All assets are inlined as Python
strings so no static directory is required.
"""

from __future__ import annotations

import datetime
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from cortexflow_ai.pwa.manifest import APP_ICON_SVG, build_manifest
from cortexflow_ai.pwa.push import PushManager, PushSubscription

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared push manager (module-level singleton; reset in tests via
# push_router.state or by patching _push_manager directly).
# ---------------------------------------------------------------------------
_push_manager = PushManager()

# ---------------------------------------------------------------------------
# Service Worker JavaScript (cache-first for static, network-first for API)
# ---------------------------------------------------------------------------
_SERVICE_WORKER_JS = r"""
const CACHE = 'cf-pwa-v1';
const STATIC = ['/app', '/manifest.json', '/app-icon-192.svg', '/app-icon-512.svg'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // Network-first for API and WebSocket upgrades
  if (url.pathname.startsWith('/api/') || url.pathname === '/ws') {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }
  // Cache-first for PWA shell assets
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request).then(resp => {
      if (resp.ok) {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
      }
      return resp;
    }))
  );
});

self.addEventListener('push', e => {
  if (!e.data) return;
  let payload;
  try { payload = e.data.json(); } catch { payload = { title: 'CortexFlow', body: e.data.text() }; }
  e.waitUntil(
    self.registration.showNotification(payload.title || 'CortexFlow', {
      body: payload.body || '',
      icon: '/app-icon-192.svg',
      badge: '/app-icon-192.svg',
      tag: payload.tag || 'cortexflow',
      data: payload.data || {}
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      const app = list.find(c => c.url.includes('/app'));
      if (app) return app.focus();
      return clients.openWindow('/app');
    })
  );
});
""".strip()

# ---------------------------------------------------------------------------
# App Shell HTML
# ---------------------------------------------------------------------------
_APP_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1a1a2e">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="CortexFlow">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/app-icon-192.svg">
<title>CortexFlow</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f0f23;--surface:#1a1a2e;--accent:#4a9eff;
  --text:#e8eaf6;--muted:#8892b0;--border:#2d2d4a;
  --radius:12px;--font:'system-ui',-apple-system,sans-serif;
}
body{background:var(--bg);color:var(--text);font-family:var(--font);
  height:100dvh;display:flex;flex-direction:column;overflow:hidden}
header{background:var(--surface);border-bottom:1px solid var(--border);
  padding:12px 16px;display:flex;align-items:center;gap:12px;
  padding-top:max(12px,env(safe-area-inset-top))}
header svg{width:32px;height:32px;flex-shrink:0}
header h1{font-size:1.1rem;font-weight:600;color:var(--text)}
#status{font-size:.75rem;color:var(--muted);margin-left:auto}
#messages{flex:1;overflow-y:auto;padding:16px;display:flex;
  flex-direction:column;gap:12px}
.msg{max-width:85%;padding:10px 14px;border-radius:var(--radius);
  font-size:.95rem;line-height:1.5;word-break:break-word}
.msg.user{background:var(--accent);color:#fff;align-self:flex-end;
  border-bottom-right-radius:4px}
.msg.ai{background:var(--surface);border:1px solid var(--border);
  align-self:flex-start;border-bottom-left-radius:4px}
.msg.ai.streaming::after{content:'▌';animation:blink .7s step-end infinite}
@keyframes blink{50%{opacity:0}}
#composer{background:var(--surface);border-top:1px solid var(--border);
  padding:12px 16px;display:flex;gap:10px;align-items:flex-end;
  padding-bottom:max(12px,env(safe-area-inset-bottom))}
#input{flex:1;background:var(--bg);border:1px solid var(--border);
  border-radius:var(--radius);color:var(--text);font-family:var(--font);
  font-size:.95rem;padding:10px 14px;resize:none;max-height:140px;
  outline:none;line-height:1.5}
#input:focus{border-color:var(--accent)}
#send{background:var(--accent);border:none;border-radius:var(--radius);
  color:#fff;cursor:pointer;font-size:1.2rem;padding:10px 16px;
  flex-shrink:0;transition:opacity .15s}
#send:disabled{opacity:.4;cursor:default}
#install-banner{display:none;background:var(--surface);border:1px solid var(--accent);
  border-radius:var(--radius);padding:12px 16px;margin:8px 16px;
  font-size:.85rem;align-items:center;gap:10px}
#install-banner button{background:var(--accent);border:none;border-radius:8px;
  color:#fff;cursor:pointer;font-size:.85rem;padding:6px 14px;white-space:nowrap}
</style>
</head>
<body>
<header>
<svg viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
  <rect width="512" height="512" rx="80" fill="#1a1a2e"/>
  <circle cx="256" cy="196" r="90" fill="#4a9eff"/>
  <path d="M110 390 Q256 490 402 390 Q345 305 256 305 Q167 305 110 390Z" fill="#4a9eff"/>
  <circle cx="256" cy="196" r="44" fill="#0f0f23"/>
  <circle cx="242" cy="188" r="13" fill="#4a9eff"/>
</svg>
<h1>CortexFlow</h1>
<span id="status">Connecting…</span>
</header>

<div id="install-banner">
  <span>Install CortexFlow for offline access</span>
  <button id="install-btn">Install</button>
  <button id="dismiss-btn" style="background:transparent;color:var(--muted)">✕</button>
</div>

<div id="messages" role="log" aria-live="polite" aria-label="Conversation"></div>

<div id="composer">
<textarea id="input" rows="1" placeholder="Message CortexFlow…"
  aria-label="Message input" autocomplete="off" spellcheck="true"></textarea>
<button id="send" aria-label="Send message" disabled>➤</button>
</div>

<script>
(function(){
'use strict';

// --- Service Worker registration ---
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(e => console.warn('SW reg failed', e));
}

// --- Install prompt ---
let deferredPrompt = null;
const banner = document.getElementById('install-banner');
const installBtn = document.getElementById('install-btn');
const dismissBtn = document.getElementById('dismiss-btn');

window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  deferredPrompt = e;
  banner.style.display = 'flex';
});
installBtn.addEventListener('click', async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  deferredPrompt = null;
  banner.style.display = 'none';
});
dismissBtn.addEventListener('click', () => { banner.style.display = 'none'; });
window.addEventListener('appinstalled', () => { banner.style.display = 'none'; deferredPrompt = null; });

// --- WebSocket ---
const statusEl = document.getElementById('status');
const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');

let ws = null;
let sessionId = null;
let currentAiMsg = null;

function wsUrl() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return proto + '://' + location.host + '/ws';
}

function connect() {
  ws = new WebSocket(wsUrl());

  ws.onopen = () => {};

  ws.onmessage = e => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }

    if (msg.type === 'hello') {
      sessionId = msg.session_id;
      statusEl.textContent = 'Connected';
      sendBtn.disabled = false;
    } else if (msg.type === 'pong') {
      // keepalive ack
    } else if (msg.type === 'message_chunk') {
      if (!currentAiMsg) {
        currentAiMsg = appendMsg('ai', '');
        currentAiMsg.classList.add('streaming');
      }
      currentAiMsg.textContent += msg.content || '';
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } else if (msg.type === 'message_done') {
      if (currentAiMsg) currentAiMsg.classList.remove('streaming');
      currentAiMsg = null;
      sendBtn.disabled = false;
    } else if (msg.type === 'message') {
      appendMsg('ai', msg.content || '');
      sendBtn.disabled = false;
    } else if (msg.type === 'error') {
      appendMsg('ai', '⚠ ' + (msg.message || 'Unknown error'));
      sendBtn.disabled = false;
    }
  };

  ws.onclose = () => {
    statusEl.textContent = 'Reconnecting…';
    sendBtn.disabled = true;
    sessionId = null;
    setTimeout(connect, 2000);
  };

  ws.onerror = () => ws.close();
}

// keepalive ping every 25s
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping' }));
  }
}, 25000);

function appendMsg(role, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  appendMsg('user', text);
  sendBtn.disabled = true;
  ws.send(JSON.stringify({ type: 'message', content: text, session_id: sessionId }));
  inputEl.value = '';
  inputEl.style.height = 'auto';
}

sendBtn.addEventListener('click', sendMessage);
inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + 'px';
});

connect();
})();
</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# PWA shell router
# ---------------------------------------------------------------------------
pwa_router = APIRouter(tags=["pwa"])


@pwa_router.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def pwa_shell() -> HTMLResponse:
    return HTMLResponse(content=_APP_HTML, status_code=200)


@pwa_router.get("/manifest.json", include_in_schema=False)
async def pwa_manifest() -> JSONResponse:
    return JSONResponse(
        content=build_manifest(),
        headers={"Content-Type": "application/manifest+json"},
    )


@pwa_router.get("/sw.js", include_in_schema=False)
async def service_worker() -> Response:
    return Response(
        content=_SERVICE_WORKER_JS,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@pwa_router.get("/app-icon-192.svg", include_in_schema=False)
async def icon_192() -> Response:
    return Response(content=APP_ICON_SVG, media_type="image/svg+xml")


@pwa_router.get("/app-icon-512.svg", include_in_schema=False)
async def icon_512() -> Response:
    return Response(content=APP_ICON_SVG, media_type="image/svg+xml")


# ---------------------------------------------------------------------------
# Push subscription router  (/api/v1/push/...)
# ---------------------------------------------------------------------------
push_router = APIRouter(prefix="/push", tags=["push"])


@push_router.get("/vapid-public-key")
async def vapid_public_key(request: Request) -> dict:
    """Return the VAPID public key stored in app state (set during startup)."""
    key = getattr(request.app.state, "vapid_public_key", None)
    if not key:
        raise HTTPException(status_code=503, detail="VAPID keys not configured")
    return {"public_key": key}


@push_router.post("/subscribe", status_code=201)
async def subscribe(request: Request) -> dict:
    """Register a Web Push subscription."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON body")

    required = {"endpoint", "p256dh", "auth"}
    missing = required - body.keys()
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing fields: {missing}")

    sub = PushSubscription(
        endpoint=body["endpoint"],
        p256dh=body["p256dh"],
        auth=body["auth"],
        user_agent=body.get("user_agent", ""),
        created_at=datetime.datetime.utcnow().isoformat() + "Z",
    )
    sid = _push_manager.add(sub)
    return {"subscription_id": sid, "status": "subscribed"}


@push_router.delete("/subscribe/{subscription_id}", status_code=200)
async def unsubscribe(subscription_id: str) -> dict:
    """Remove a Web Push subscription by ID."""
    removed = _push_manager.remove(subscription_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"status": "unsubscribed"}


@push_router.get("/subscriptions")
async def list_subscriptions() -> dict:
    """Return summary of active push subscriptions (admin)."""
    subs = _push_manager.list_all()
    return {
        "count": len(subs),
        "subscriptions": [
            {
                "id": s.subscription_id,
                "endpoint": s.endpoint[:60] + "…" if len(s.endpoint) > 60 else s.endpoint,
                "created_at": s.created_at,
            }
            for s in subs
        ],
    }


@push_router.post("/notify")
async def notify_all(request: Request) -> dict:
    """Send a push notification to all subscribers (admin / internal use)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON body")

    title = body.get("title", "CortexFlow")
    message_body = body.get("body", "")

    subs = _push_manager.list_all()
    if not subs:
        return {"sent": 0, "message": "No active subscribers"}

    # Payload built here; actual WebPush send requires pywebpush + VAPID keys.
    # This endpoint returns the payload structure for now; a full send would
    # require the cryptography + pywebpush libraries and is wired separately.
    payload = json.dumps({"title": title, "body": message_body})
    return {
        "sent": len(subs),
        "payload_size": len(payload),
        "note": "Delivery requires pywebpush integration",
    }

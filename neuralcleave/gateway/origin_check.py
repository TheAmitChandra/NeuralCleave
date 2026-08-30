"""Shared WebSocket origin allow-list.

Starlette's ``CORSMiddleware`` — the only origin restriction this gateway
had — never applies to WebSocket connections at all; it only wraps HTTP
scope and passes every other ASGI scope straight through unchecked. That
left every ``/ws/*`` route (the main chat socket, the voice stream, and the
embedded terminal) reachable by any page a user's browser has open, with no
origin restriction whatsoever, regardless of ``CORSMiddleware``'s
``allow_origins`` configuration (round 6 gap analysis 5.2, 2026-08-29).

This module is the single source of truth for the origin allow-list, built
once from config in ``create_app()`` and consulted both by
``CORSMiddleware`` (for HTTP) and by each WebSocket handler (for the
handshake) — so the two can never silently drift apart the way a duplicated
list would.

Usage::

    from neuralcleave.gateway.origin_check import (
        allowed_origins, is_allowed_origin, set_allowed_origins,
    )

    # In create_app():
    set_allowed_origins(cfg)
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(cfg), ...)

    # In a WebSocket handler, before accept():
    if not is_allowed_origin(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return
"""

from __future__ import annotations

import re

from neuralcleave.config import NeuralCleaveConfig

# Matches the same set of dev-server / Tauri virtual-host origins
# CORSMiddleware's own allow_origin_regex already permits. 127.0.0.1 and
# localhost are the same host to every browser, so both must be accepted
# on any port - round 7 gap analysis 3 (2026-08-30) found the regex only
# covered "localhost", so a page served on the gateway's own port via its
# loopback IP (e.g. the /canvas page at http://127.0.0.1:7432/canvas) had
# its WebSocket rejected even though the identical http://localhost:7432
# origin was allowed.
ORIGIN_REGEX = re.compile(r"https?://(tauri\.)?(localhost|127\.0\.0\.1)(:\d+)?")

_allowed: list[str] = []


def allowed_origins(cfg: NeuralCleaveConfig) -> list[str]:
    """The exact origin allow-list used for both CORSMiddleware and the
    WebSocket-level check below."""
    return [
        f"http://localhost:{cfg.ui.web_port}",
        f"http://127.0.0.1:{cfg.ui.web_port}",
        "http://tauri.localhost",             # Tauri v2.11+ Windows (WebView2 virtual host)
        "https://tauri.localhost",            # Tauri v2 Windows older builds
        "https://com.neuralcleave.desktop",   # Tauri v2 Windows identifier-based
        "tauri://localhost",                  # Tauri v2 macOS/Linux
    ]


def set_allowed_origins(cfg: NeuralCleaveConfig) -> None:
    """Populate the allow-list consulted by ``is_allowed_origin`` — call
    once from ``create_app()`` before any WebSocket route can be reached."""
    global _allowed
    _allowed = allowed_origins(cfg)


def is_allowed_origin(origin: str | None) -> bool:
    """Whether *origin* is safe to accept a WebSocket handshake from.

    A **missing** Origin header is allowed: a real browser always sends one
    for a cross-origin WebSocket handshake (this is mandated by the
    WebSocket protocol, not something a malicious page's JS can suppress),
    so the actual cross-site-hijacking attack this check exists to stop
    always presents *some* origin — the attacker's own, which won't match
    the allow-list below. Only non-browser local tools (a test client, a
    dev script) legitimately omit it; the same threat model this project
    already accepts for a personal-use, 127.0.0.1-bound desktop tool.

    A **present but mismatched** origin is always rejected.
    """
    if not origin:
        return True
    if origin in _allowed:
        return True
    return bool(ORIGIN_REGEX.fullmatch(origin))

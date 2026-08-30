"""Tests for neuralcleave.gateway.origin_check.

Round 6 gap analysis 5.2 (2026-08-29): Starlette's CORSMiddleware never
applies to WebSocket connections, so this module is the only real origin
restriction any /ws/* route gets.
"""

from __future__ import annotations

import pytest

from neuralcleave.config import NeuralCleaveConfig
from neuralcleave.gateway.origin_check import (
    allowed_origins,
    is_allowed_origin,
    set_allowed_origins,
)


@pytest.fixture(autouse=True)
def reset_allowed_origins():
    """Isolate each test's allow-list from whatever another test/module set."""
    set_allowed_origins(NeuralCleaveConfig())
    yield
    set_allowed_origins(NeuralCleaveConfig())


class TestAllowedOrigins:
    def test_includes_the_configured_web_port(self):
        cfg = NeuralCleaveConfig()
        cfg.ui.web_port = 4321
        origins = allowed_origins(cfg)
        assert "http://localhost:4321" in origins
        assert "http://127.0.0.1:4321" in origins

    def test_includes_the_tauri_origins(self):
        origins = allowed_origins(NeuralCleaveConfig())
        assert "tauri://localhost" in origins
        assert "http://tauri.localhost" in origins
        assert "https://tauri.localhost" in origins
        assert "https://com.neuralcleave.desktop" in origins


class TestIsAllowedOrigin:
    def test_missing_origin_is_allowed(self):
        """A real browser always sends Origin for a cross-origin WebSocket
        handshake - the attack this check exists to stop always presents
        some (mismatched) origin. Only non-browser local tools omit it."""
        assert is_allowed_origin(None) is True
        assert is_allowed_origin("") is True

    def test_configured_web_port_origin_is_allowed(self):
        cfg = NeuralCleaveConfig()
        cfg.ui.web_port = 3000
        set_allowed_origins(cfg)
        assert is_allowed_origin("http://localhost:3000") is True
        assert is_allowed_origin("http://127.0.0.1:3000") is True

    def test_tauri_origins_are_allowed(self):
        assert is_allowed_origin("tauri://localhost") is True
        assert is_allowed_origin("http://tauri.localhost") is True
        assert is_allowed_origin("https://tauri.localhost:5173") is True

    def test_arbitrary_origin_is_rejected(self):
        assert is_allowed_origin("https://evil.example.com") is False

    def test_a_different_localhost_port_than_configured_is_still_allowed_by_regex(self):
        """Matches CORSMiddleware's own allow_origin_regex behavior - any
        localhost port, not just the configured one (covers the dev
        server running on a different port)."""
        assert is_allowed_origin("http://localhost:9999") is True

    def test_a_different_127_0_0_1_port_than_configured_is_still_allowed_by_regex(self):
        """Round 7 gap analysis 3 (2026-08-30): 127.0.0.1 and localhost are
        the same host to every browser, so a page served on the gateway's
        own port via its loopback IP (e.g. /canvas at
        http://127.0.0.1:7432/canvas) must be allowed exactly like the
        equivalent localhost origin - not just the configured ui.web_port's
        literal 127.0.0.1 entry."""
        assert is_allowed_origin("http://127.0.0.1:7432") is True
        assert is_allowed_origin("http://127.0.0.1:9999") is True

    def test_lookalike_origin_is_rejected(self):
        """A regex/substring-matching bug would be its own vulnerability -
        a domain that merely contains "localhost" must not pass."""
        assert is_allowed_origin("https://localhost.evil.example.com") is False
        assert is_allowed_origin("https://evil-localhost.com") is False
        assert is_allowed_origin("https://127.0.0.1.evil.example.com") is False

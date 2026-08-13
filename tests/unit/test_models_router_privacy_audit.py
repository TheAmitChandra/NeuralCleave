"""Tests proving ModelRouter's httpx call sites are wired to the privacy audit log.

Before this wiring, neuralcleave/privacy/middleware.py's AuditTransport was
fully implemented but never referenced outside its own module, so
AUDIT_LOG (and therefore GET /api/v1/privacy/report) always stayed empty
regardless of real outbound provider traffic. These tests exercise the real
_audited_client() helper and the session-id contextvar set by
generate()/generate_stream(), rather than re-testing AuditTransport itself
(already covered by test_privacy_middleware.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from neuralcleave.models.router import (
    _AUDIT_SESSION_ID,
    GenerationResult,
    ModelRouter,
    StreamChunk,
)
from neuralcleave.privacy.audit import PrivacyAuditLog


def _ok_response(body: dict) -> httpx.Response:
    return httpx.Response(200, json=body, request=httpx.Request("POST", "http://x"))


class TestAuditedClient:
    def test_returns_httpx_async_client(self) -> None:
        router = ModelRouter()
        client = router._audited_client()
        assert isinstance(client, httpx.AsyncClient)

    def test_default_session_id_is_default(self) -> None:
        assert _AUDIT_SESSION_ID.get() == "default"


class TestOllamaCallRecordsAuditEntry:
    """End-to-end: a real provider call site (_ollama) through a real
    AuditTransport wrapping a faked inner transport, proving requests really
    reach AUDIT_LOG rather than just proving _audited_client() doesn't crash."""

    @pytest.mark.asyncio
    async def test_ollama_call_records_entry_with_session_id(self) -> None:
        fresh_log = PrivacyAuditLog()
        fake_inner = AsyncMock(spec=httpx.AsyncBaseTransport)
        fake_inner.handle_async_request = AsyncMock(
            return_value=_ok_response({"response": "hi there", "done": True, "prompt_eval_count": 3, "eval_count": 2})
        )
        fake_inner.aclose = AsyncMock()

        router = ModelRouter(ollama_base_url="http://localhost:11434")
        with (
            patch("neuralcleave.models.router.AUDIT_LOG", fresh_log),
            patch("httpx.AsyncHTTPTransport", return_value=fake_inner),
        ):
            token = _AUDIT_SESSION_ID.set("session-xyz")
            try:
                await router._ollama("llama3.2:1b", prompt="hi", system=None, max_tokens=10)
            finally:
                _AUDIT_SESSION_ID.reset(token)

        entries = fresh_log.entries_for_session("session-xyz")
        assert len(entries) == 1
        assert entries[0].url == "http://localhost:11434/api/generate"
        assert entries[0].method == "POST"

    @pytest.mark.asyncio
    async def test_ollama_call_with_no_session_falls_back_to_default(self) -> None:
        fresh_log = PrivacyAuditLog()
        fake_inner = AsyncMock(spec=httpx.AsyncBaseTransport)
        fake_inner.handle_async_request = AsyncMock(
            return_value=_ok_response({"response": "hi", "done": True})
        )
        fake_inner.aclose = AsyncMock()

        router = ModelRouter(ollama_base_url="http://localhost:11434")
        with (
            patch("neuralcleave.models.router.AUDIT_LOG", fresh_log),
            patch("httpx.AsyncHTTPTransport", return_value=fake_inner),
        ):
            await router._ollama("llama3.2:1b", prompt="hi", system=None, max_tokens=10)

        assert len(fresh_log.entries_for_session("default")) == 1


class TestGenerateSetsSessionContext:
    @pytest.mark.asyncio
    async def test_generate_sets_session_id_during_call_and_resets_after(self) -> None:
        router = ModelRouter()
        seen: dict[str, str] = {}

        async def fake_call(*_args, **_kwargs):
            seen["during"] = _AUDIT_SESSION_ID.get()
            return GenerationResult(text="ok", model="m", provider="ollama")

        with patch.object(router, "_call", side_effect=fake_call):
            await router.generate("hi", session_id="my-session")

        assert seen["during"] == "my-session"
        assert _AUDIT_SESSION_ID.get() == "default"

    @pytest.mark.asyncio
    async def test_generate_without_session_id_defaults(self) -> None:
        router = ModelRouter()
        seen: dict[str, str] = {}

        async def fake_call(*_args, **_kwargs):
            seen["during"] = _AUDIT_SESSION_ID.get()
            return GenerationResult(text="ok", model="m", provider="ollama")

        with patch.object(router, "_call", side_effect=fake_call):
            await router.generate("hi")

        assert seen["during"] == "default"

    @pytest.mark.asyncio
    async def test_generate_resets_session_id_even_when_all_providers_fail(self) -> None:
        router = ModelRouter()

        async def failing_call(*_args, **_kwargs):
            raise RuntimeError("boom")

        with patch.object(router, "_call", side_effect=failing_call):
            with pytest.raises(RuntimeError):
                await router.generate("hi", session_id="doomed-session")

        assert _AUDIT_SESSION_ID.get() == "default"


class TestGenerateStreamSetsSessionContext:
    @pytest.mark.asyncio
    async def test_generate_stream_sets_session_id_during_call_and_resets_after(self) -> None:
        router = ModelRouter()
        seen: dict[str, str] = {}

        async def fake_call_stream(*_args, **_kwargs):
            seen["during"] = _AUDIT_SESSION_ID.get()
            yield StreamChunk(text="hi", model="m", provider="ollama")
            yield StreamChunk(done=True, model="m", provider="ollama")

        with patch.object(router, "_call_stream", side_effect=fake_call_stream):
            async for _ in router.generate_stream("hi", session_id="stream-session"):
                pass

        assert seen["during"] == "stream-session"
        assert _AUDIT_SESSION_ID.get() == "default"

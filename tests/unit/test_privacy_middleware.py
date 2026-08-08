"""Tests for AuditTransport HTTPX middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from neuralcleave.privacy.audit import PrivacyAuditLog
from neuralcleave.privacy.middleware import AuditTransport


def _make_transport(log: PrivacyAuditLog, session: str = "s1") -> AuditTransport:
    inner = AsyncMock(spec=httpx.AsyncBaseTransport)
    fake_response = httpx.Response(200, content=b"ok")
    inner.handle_async_request = AsyncMock(return_value=fake_response)
    inner.aclose = AsyncMock()
    return AuditTransport(inner, log, session_id=session)


class TestAuditTransport:
    @pytest.mark.asyncio
    async def test_records_request_url_in_audit_log(self) -> None:
        log = PrivacyAuditLog()
        transport = _make_transport(log, session="abc")

        request = httpx.Request("GET", "https://api.openai.com/v1/models")
        await transport.handle_async_request(request)

        entries = log.entries_for_session("abc")
        assert len(entries) == 1
        assert entries[0].url == "https://api.openai.com/v1/models"

    @pytest.mark.asyncio
    async def test_records_request_method(self) -> None:
        log = PrivacyAuditLog()
        transport = _make_transport(log)

        request = httpx.Request("POST", "https://example.com/endpoint")
        await transport.handle_async_request(request)

        entries = log.all_entries()
        assert entries[0].method == "POST"

    @pytest.mark.asyncio
    async def test_records_session_id_on_entry(self) -> None:
        log = PrivacyAuditLog()
        transport = _make_transport(log, session="my-session")

        request = httpx.Request("GET", "https://x.com")
        await transport.handle_async_request(request)

        assert log.entries_for_session("my-session")[0].session_id == "my-session"

    @pytest.mark.asyncio
    async def test_delegates_to_inner_transport(self) -> None:
        log = PrivacyAuditLog()
        inner = AsyncMock(spec=httpx.AsyncBaseTransport)
        inner.handle_async_request = AsyncMock(return_value=httpx.Response(201, content=b"created"))
        inner.aclose = AsyncMock()
        transport = AuditTransport(inner, log, session_id="s")

        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        resp = await transport.handle_async_request(request)

        assert resp.status_code == 201
        inner.handle_async_request.assert_awaited_once_with(request)

    @pytest.mark.asyncio
    async def test_records_entry_even_if_inner_raises(self) -> None:
        log = PrivacyAuditLog()
        inner = MagicMock(spec=httpx.AsyncBaseTransport)
        inner.handle_async_request = AsyncMock(side_effect=httpx.ConnectError("timeout"))
        transport = AuditTransport(inner, log, session_id="s")

        request = httpx.Request("GET", "https://failing.example.com")
        with pytest.raises(httpx.ConnectError):
            await transport.handle_async_request(request)

        # Entry was still recorded before the inner transport raised
        assert len(log.all_entries()) == 1
        assert log.all_entries()[0].url == "https://failing.example.com"

    @pytest.mark.asyncio
    async def test_aclose_delegates_to_inner(self) -> None:
        log = PrivacyAuditLog()
        inner = AsyncMock(spec=httpx.AsyncBaseTransport)
        inner.aclose = AsyncMock()
        transport = AuditTransport(inner, log, session_id="s")

        await transport.aclose()
        inner.aclose.assert_awaited_once()

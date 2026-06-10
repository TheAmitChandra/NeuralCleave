"""Unit tests for cortexflow.channels.teams — TeamsAdapter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow.channels.teams import TeamsAdapter


def make_adapter(**overrides) -> TeamsAdapter:
    cfg = {
        "app_id": "app-id-test",
        "app_password": "secret-pw",
        "webhook_port": 19435,
        "path": "/teams/messages",
        **overrides,
    }
    return TeamsAdapter(cfg)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construction_defaults():
    adapter = make_adapter()
    assert adapter.channel_id == "teams"
    assert adapter._webhook_port == 19435
    assert adapter._path == "/teams/messages"


def test_construction_env_resolution(monkeypatch):
    monkeypatch.setenv("TEAMS_TEST_ID", "resolved-app-id")
    adapter = TeamsAdapter({"app_id": "ENV:TEAMS_TEST_ID", "app_password": "pw"})
    assert adapter._app_id == "resolved-app-id"


def test_construction_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("TEAMS_NO_SUCH_VAR", raising=False)
    adapter = TeamsAdapter({"app_id": "ENV:TEAMS_NO_SUCH_VAR", "app_password": "pw"})
    assert adapter._app_id == ""


# ---------------------------------------------------------------------------
# get_config_schema
# ---------------------------------------------------------------------------


def test_config_schema_has_required_fields():
    schema = make_adapter().get_config_schema()
    assert "app_id" in schema["required"]
    assert "app_password" in schema["required"]


# ---------------------------------------------------------------------------
# send — invalid target
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_invalid_target_returns_none():
    adapter = make_adapter()
    result = await adapter.send("no-pipe-here", "hello")
    assert result is None


# ---------------------------------------------------------------------------
# send — no credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_credentials_returns_none():
    adapter = TeamsAdapter({"app_id": "", "app_password": ""})
    result = await adapter.send("https://smba.trafficmanager.net|conv123", "hi")
    assert result is None


# ---------------------------------------------------------------------------
# _get_token — no credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_token_no_credentials_returns_none():
    adapter = TeamsAdapter({"app_id": "", "app_password": ""})
    token = await adapter._get_token()
    assert token is None


# ---------------------------------------------------------------------------
# _get_token — HTTP error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_token_http_error_returns_none():
    adapter = make_adapter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("401 Unauthorized"))

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        token = await adapter._get_token()
    assert token is None


# ---------------------------------------------------------------------------
# Fake request helper
# ---------------------------------------------------------------------------


def make_fake_request(body_dict: dict) -> MagicMock:
    """Return a fake aiohttp request whose .json() coroutine returns body_dict."""
    req = MagicMock()
    req.json = AsyncMock(return_value=body_dict)
    return req


# ---------------------------------------------------------------------------
# _handle_activity — non-message activity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_activity_non_message_returns_200():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    request = make_fake_request({"type": "conversationUpdate"})
    response = await adapter._handle_activity(request)
    assert response.status == 200
    assert len(dispatched) == 0


# ---------------------------------------------------------------------------
# _handle_activity — valid message activity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_activity_message_dispatches():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    request = make_fake_request({
        "type": "message",
        "text": "Hello Teams!",
        "from": {"id": "user-1", "name": "Alice"},
        "serviceUrl": "https://smba.trafficmanager.net",
        "conversation": {"id": "conv-abc"},
    })
    response = await adapter._handle_activity(request)
    assert response.status == 200

    await asyncio.sleep(0)  # let create_task run
    assert len(dispatched) == 1
    assert dispatched[0].text == "Hello Teams!"
    assert dispatched[0].sender_id == "user-1"


# ---------------------------------------------------------------------------
# _health — always returns 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_200():
    adapter = make_adapter()
    request = MagicMock()
    response = await adapter._health(request)
    assert response.status == 200

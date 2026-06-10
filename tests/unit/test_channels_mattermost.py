"""Unit tests for cortexflow.channels.mattermost — MattermostAdapter."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow.channels.mattermost import MattermostAdapter


def make_adapter(**overrides) -> MattermostAdapter:
    cfg = {
        "url": "http://localhost:8065",
        "token": "test-token-xyz",
        "channel": "town-square",
        **overrides,
    }
    return MattermostAdapter(cfg)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construction_defaults():
    adapter = make_adapter()
    assert adapter.channel_id == "mattermost"
    assert adapter._url == "http://localhost:8065"
    assert adapter._channel_name == "town-square"


def test_url_trailing_slash_stripped():
    adapter = make_adapter(url="http://mattermost.example.com/")
    assert adapter._url == "http://mattermost.example.com"


def test_construction_env_resolution(monkeypatch):
    monkeypatch.setenv("MM_TOKEN_TEST", "resolved-token")
    adapter = MattermostAdapter({"token": "ENV:MM_TOKEN_TEST"})
    assert adapter._token == "resolved-token"


def test_construction_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("MM_NO_SUCH_TOKEN", raising=False)
    adapter = MattermostAdapter({"token": "ENV:MM_NO_SUCH_TOKEN"})
    assert adapter._token == ""


# ---------------------------------------------------------------------------
# get_config_schema
# ---------------------------------------------------------------------------


def test_config_schema_requires_token():
    schema = make_adapter().get_config_schema()
    assert "token" in schema["required"]


# ---------------------------------------------------------------------------
# send — no token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_token_returns_none():
    adapter = make_adapter(token="")
    result = await adapter.send("channel-id-123", "hello")
    assert result is None


# ---------------------------------------------------------------------------
# send — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_success_returns_post_id():
    adapter = make_adapter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"id": "post-xyz-789"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("channel-123", "Hello Mattermost!")

    assert result == "post-xyz-789"


# ---------------------------------------------------------------------------
# send — HTTP error returns None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_http_error_returns_none():
    adapter = make_adapter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("503 Service Unavailable"))

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("channel-123", "hello")

    assert result is None


# ---------------------------------------------------------------------------
# _fetch_bot_user_id — no token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_bot_user_id_no_token_returns_none():
    adapter = make_adapter(token="")
    result = await adapter._fetch_bot_user_id()
    assert result is None


# ---------------------------------------------------------------------------
# _process_event — non-posted event is ignored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_event_ignores_non_posted():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._process_event({"event": "user_added", "data": {}})
    assert len(dispatched) == 0


# ---------------------------------------------------------------------------
# _process_event — own message is filtered out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_event_filters_own_messages():
    adapter = make_adapter()
    adapter._bot_user_id = "bot-user-id"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    post = {"user_id": "bot-user-id", "channel_id": "ch1", "message": "I said this"}
    await adapter._process_event({"event": "posted", "data": {"post": json.dumps(post)}})
    assert len(dispatched) == 0


# ---------------------------------------------------------------------------
# _process_event — valid message is dispatched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_event_dispatches_inbound_message():
    adapter = make_adapter()
    adapter._bot_user_id = "bot-user-id"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    post = {
        "user_id": "alice",
        "channel_id": "ch1",
        "message": "Hey bot, what's up?",
    }
    event = {
        "event": "posted",
        "data": {
            "post": json.dumps(post),
            "sender_name": "@alice",
        },
    }
    await adapter._process_event(event)
    await asyncio.sleep(0)  # let create_task run

    assert len(dispatched) == 1
    assert dispatched[0].text == "Hey bot, what's up?"
    assert dispatched[0].sender_id == "alice"
    assert dispatched[0].sender_name == "alice"

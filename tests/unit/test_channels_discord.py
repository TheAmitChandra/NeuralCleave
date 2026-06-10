"""Unit tests for cortexflow.channels.discord_ — DiscordAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cortexflow.channels.discord_ import DiscordAdapter, _guess_type


def make_adapter(**overrides) -> DiscordAdapter:
    cfg = {"bot_token": "test-discord-token", **overrides}
    return DiscordAdapter(cfg)


# ---------------------------------------------------------------------------
# Construction & _resolve
# ---------------------------------------------------------------------------


def test_construction_defaults():
    adapter = make_adapter()
    assert adapter.channel_id == "discord"
    assert adapter._client is None
    assert adapter._task is None


def test_resolve_plain_string():
    assert DiscordAdapter({})._resolve("plain-value") == "plain-value"


def test_resolve_env_var(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN_TEST", "env-discord-token")
    assert DiscordAdapter({})._resolve("ENV:DISCORD_BOT_TOKEN_TEST") == "env-discord-token"


def test_resolve_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("DISCORD_NO_SUCH", raising=False)
    assert DiscordAdapter({})._resolve("ENV:DISCORD_NO_SUCH") == ""


# ---------------------------------------------------------------------------
# get_config_schema
# ---------------------------------------------------------------------------


def test_config_schema_required_fields():
    schema = make_adapter().get_config_schema()
    assert "bot_token" in schema["required"]


def test_config_schema_has_prefix_property():
    schema = make_adapter().get_config_schema()
    assert "prefix" in schema["properties"]


# ---------------------------------------------------------------------------
# _guess_type
# ---------------------------------------------------------------------------


def test_guess_type_image():
    assert _guess_type("image/png") == "image"


def test_guess_type_audio():
    assert _guess_type("audio/mpeg") == "audio"


def test_guess_type_video():
    assert _guess_type("video/mp4") == "video"


def test_guess_type_document():
    assert _guess_type("application/pdf") == "document"


def test_guess_type_empty():
    assert _guess_type("") == "document"


# ---------------------------------------------------------------------------
# disconnect — safe when nothing connected
# ---------------------------------------------------------------------------


async def test_disconnect_when_not_connected_is_safe():
    adapter = make_adapter()
    await adapter.disconnect()  # should not raise
    assert adapter._client is None
    assert adapter._task is None


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


async def test_send_no_client_raises():
    adapter = make_adapter()
    with pytest.raises(RuntimeError, match="connect"):
        await adapter.send("123456789", "hello")


async def test_send_success_returns_message_id():
    adapter = make_adapter()
    mock_msg = MagicMock()
    mock_msg.id = 777
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock(return_value=mock_msg)
    mock_client = MagicMock()
    mock_client.get_channel = MagicMock(return_value=mock_channel)
    adapter._client = mock_client

    result = await adapter.send("123456789", "Hello Discord!")
    assert result == "777"
    mock_channel.send.assert_called_once_with(content="Hello Discord!")


async def test_send_fetches_channel_when_get_returns_none():
    adapter = make_adapter()
    mock_msg = MagicMock()
    mock_msg.id = 888
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock(return_value=mock_msg)
    mock_client = MagicMock()
    # get_channel returns None → falls back to fetch_channel
    mock_client.get_channel = MagicMock(return_value=None)
    mock_client.fetch_channel = AsyncMock(return_value=mock_channel)
    adapter._client = mock_client

    result = await adapter.send("123456789", "fallback send")
    assert result == "888"


async def test_send_error_returns_none():
    adapter = make_adapter()
    mock_client = MagicMock()
    mock_client.get_channel = MagicMock(side_effect=Exception("channel error"))
    adapter._client = mock_client

    result = await adapter.send("bad-id", "fail")
    assert result is None

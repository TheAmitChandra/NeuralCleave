"""Unit tests for cortexflow.channels.discord_ — DiscordAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.channels.discord_ import DiscordAdapter, _guess_type


class _FakeIntents:
    def __init__(self) -> None:
        self.message_content = False
        self.dm_messages = False


class _FakeDiscordClient:
    """Stand-in for discord.Client — a plain subclassable base."""

    def __init__(self, **kwargs) -> None:
        self._kwargs = kwargs
        self.user = MagicMock(name="bot-user")

    async def start(self, token: str) -> None:
        pass  # real discord.py blocks forever here; tests don't need that

    async def close(self) -> None:
        pass


def _mock_discord_module() -> MagicMock:
    mock_discord = MagicMock()
    mock_discord.Client = _FakeDiscordClient
    mock_discord.Intents.default = MagicMock(return_value=_FakeIntents())
    return mock_discord


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


async def test_send_no_client_returns_none():
    """Regression: send() must return None when not connected, not raise."""
    adapter = make_adapter()
    result = await adapter.send("123456789", "hello")
    assert result is None


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


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


async def test_connect_raises_if_discord_not_installed():
    adapter = make_adapter()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "discord":
            raise ImportError("No module named 'discord'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="discord.py"):
            await adapter.connect()


async def test_connect_raises_if_no_bot_token():
    adapter = DiscordAdapter({})
    with patch.dict("sys.modules", {"discord": _mock_discord_module()}):
        with pytest.raises(ValueError, match="bot_token"):
            await adapter.connect()


async def test_connect_success_creates_client_and_task():
    adapter = make_adapter()

    with patch.dict("sys.modules", {"discord": _mock_discord_module()}):
        await adapter.connect()

    assert adapter._client is not None
    assert adapter._task is not None

    await adapter.disconnect()


# ---------------------------------------------------------------------------
# _BotClient.on_message — via the real connect()ed client instance
# ---------------------------------------------------------------------------


def _make_fake_message(**overrides) -> MagicMock:
    author = MagicMock()
    author.id = 12345
    author.display_name = "Alice"

    channel = MagicMock()
    channel.id = 999

    msg = MagicMock()
    msg.author = author
    msg.content = "Hello bot"
    msg.attachments = []
    msg.channel = channel
    msg.reference = None
    msg.guild = None
    for key, value in overrides.items():
        setattr(msg, key, value)
    return msg


async def test_on_message_skips_own_messages():
    adapter = make_adapter()
    with patch.dict("sys.modules", {"discord": _mock_discord_module()}):
        await adapter.connect()

    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    own_message = _make_fake_message(author=adapter._client.user)
    await adapter._client.on_message(own_message)

    assert dispatched == []
    await adapter.disconnect()


async def test_on_message_dispatches_inbound():
    adapter = make_adapter()
    with patch.dict("sys.modules", {"discord": _mock_discord_module()}):
        await adapter.connect()

    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    message = _make_fake_message()
    await adapter._client.on_message(message)

    assert len(dispatched) == 1
    assert dispatched[0].sender_id == "12345"
    assert dispatched[0].sender_name == "Alice"
    assert dispatched[0].text == "Hello bot"
    assert dispatched[0].thread_id == "999"
    assert dispatched[0].reply_to_id is None
    assert dispatched[0].raw["guild_id"] is None

    await adapter.disconnect()


async def test_on_message_includes_reply_and_guild():
    adapter = make_adapter()
    with patch.dict("sys.modules", {"discord": _mock_discord_module()}):
        await adapter.connect()

    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    reference = MagicMock()
    reference.message_id = 555
    guild = MagicMock()
    guild.id = 42

    message = _make_fake_message(reference=reference, guild=guild)
    await adapter._client.on_message(message)

    assert dispatched[0].reply_to_id == "555"
    assert dispatched[0].raw["guild_id"] == "42"

    await adapter.disconnect()


async def test_on_message_builds_attachments():
    adapter = make_adapter()
    with patch.dict("sys.modules", {"discord": _mock_discord_module()}):
        await adapter.connect()

    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    attachment = MagicMock()
    attachment.content_type = "image/png"
    attachment.url = "https://cdn.discord.com/pic.png"
    attachment.filename = "pic.png"

    message = _make_fake_message(attachments=[attachment])
    await adapter._client.on_message(message)

    assert len(dispatched[0].attachments) == 1
    assert dispatched[0].attachments[0].type == "image"
    assert dispatched[0].attachments[0].filename == "pic.png"

    await adapter.disconnect()


async def test_on_ready_does_not_raise():
    adapter = make_adapter()
    with patch.dict("sys.modules", {"discord": _mock_discord_module()}):
        await adapter.connect()

    await adapter._client.on_ready()  # should not raise
    await adapter.disconnect()


# ---------------------------------------------------------------------------
# disconnect() — with an active client/task
# ---------------------------------------------------------------------------


async def test_disconnect_closes_client_and_cancels_task():
    adapter = make_adapter()
    with patch.dict("sys.modules", {"discord": _mock_discord_module()}):
        await adapter.connect()

    await adapter.disconnect()

    assert adapter._client is None
    assert adapter._task is None

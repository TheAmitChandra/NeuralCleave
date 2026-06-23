"""Unit tests for cortexflow.channels.telegram — TelegramAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cortexflow.channels.telegram import TelegramAdapter


def make_adapter(**overrides) -> TelegramAdapter:
    cfg = {"bot_token": "test-token-123", **overrides}
    return TelegramAdapter(cfg)


def _make_update(
    *,
    text: str | None = "Hello bot",
    user_id: int = 555,
    user_name: str = "Alice",
    chat_id: int = 999,
    voice: bool = False,
    photo: bool = False,
    document: bool = False,
    reply_to_id: int | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Return (update, context) mocks for _on_update."""
    user = MagicMock()
    user.id = user_id
    user.full_name = user_name

    msg = MagicMock()
    msg.text = text
    msg.caption = None
    msg.from_user = user
    msg.chat_id = chat_id
    if voice:
        msg.voice = MagicMock()
        msg.voice.file_id = "voice-file-id"
    else:
        msg.voice = None
    msg.photo = None
    msg.document = None
    msg.reply_to_message = None

    if photo:
        photo_obj = MagicMock()
        photo_obj.file_id = "photo-file-id"
        msg.photo = [photo_obj]

    if document:
        doc = MagicMock()
        doc.file_name = "report.pdf"
        doc.mime_type = "application/pdf"
        msg.document = doc

    if reply_to_id is not None:
        reply_ref = MagicMock()
        reply_ref.message_id = reply_to_id
        msg.reply_to_message = reply_ref

    update = MagicMock()
    update.message = msg
    update.update_id = 1

    context = MagicMock()
    mock_file = MagicMock()
    mock_file.file_path = "https://api.telegram.org/file/photo.jpg"
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"oggdata"))
    context.bot.get_file = AsyncMock(return_value=mock_file)

    return update, context


# ---------------------------------------------------------------------------
# Construction & _resolve
# ---------------------------------------------------------------------------


def test_construction_defaults():
    adapter = make_adapter()
    assert adapter.channel_id == "telegram"
    assert adapter._app is None


def test_resolve_plain_string():
    assert TelegramAdapter({})._resolve("plain-value") == "plain-value"


def test_resolve_env_var(monkeypatch):
    monkeypatch.setenv("TG_BOT_TOKEN_TEST", "env-token-value")
    assert TelegramAdapter({})._resolve("ENV:TG_BOT_TOKEN_TEST") == "env-token-value"


def test_resolve_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("TG_NO_SUCH_VAR", raising=False)
    assert TelegramAdapter({})._resolve("ENV:TG_NO_SUCH_VAR") == ""


# ---------------------------------------------------------------------------
# get_config_schema
# ---------------------------------------------------------------------------


def test_config_schema_required_fields():
    schema = make_adapter().get_config_schema()
    assert "bot_token" in schema["required"]


def test_config_schema_has_enabled_property():
    schema = make_adapter().get_config_schema()
    assert "enabled" in schema["properties"]


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


async def test_send_no_app_raises():
    adapter = make_adapter()
    with pytest.raises(RuntimeError, match="connect"):
        await adapter.send("123456", "hello")


async def test_send_success_returns_message_id():
    adapter = make_adapter()
    mock_msg = MagicMock()
    mock_msg.message_id = 99
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=mock_msg)
    mock_app = MagicMock()
    mock_app.bot = mock_bot
    adapter._app = mock_app

    result = await adapter.send("123456", "Hello Telegram!")
    assert result == "99"
    mock_bot.send_message.assert_called_once()


async def test_send_with_reply_to():
    adapter = make_adapter()
    mock_msg = MagicMock()
    mock_msg.message_id = 42
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=mock_msg)
    mock_app = MagicMock()
    mock_app.bot = mock_bot
    adapter._app = mock_app

    await adapter.send("123456", "reply", reply_to="7")
    call_kwargs = mock_bot.send_message.call_args[1]
    assert call_kwargs["reply_to_message_id"] == 7


async def test_send_error_returns_none():
    adapter = make_adapter()
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(side_effect=Exception("API error"))
    mock_app = MagicMock()
    mock_app.bot = mock_bot
    adapter._app = mock_app

    result = await adapter.send("123456", "fail")
    assert result is None


async def test_send_with_audio_attachment_sends_voice():
    from cortexflow.channels.base import Attachment

    adapter = make_adapter()
    mock_msg = MagicMock()
    mock_msg.message_id = 11
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=mock_msg)
    mock_bot.send_voice = AsyncMock()
    mock_app = MagicMock()
    mock_app.bot = mock_bot
    adapter._app = mock_app

    await adapter.send(
        "123456", "transcript text",
        attachments=[Attachment(type="audio", data=b"replyaudio", mime_type="audio/mpeg")],
    )

    mock_bot.send_voice.assert_called_once()
    assert mock_bot.send_voice.call_args[1]["voice"] == b"replyaudio"


async def test_send_without_audio_attachment_skips_send_voice():
    adapter = make_adapter()
    mock_msg = MagicMock()
    mock_msg.message_id = 12
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=mock_msg)
    mock_bot.send_voice = AsyncMock()
    mock_app = MagicMock()
    mock_app.bot = mock_bot
    adapter._app = mock_app

    await adapter.send("123456", "text only")

    mock_bot.send_voice.assert_not_called()


# ---------------------------------------------------------------------------
# _on_update — dispatch
# ---------------------------------------------------------------------------


async def test_on_update_none_message_skips():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    update = MagicMock()
    update.message = None
    await adapter._on_update(update, MagicMock())
    assert len(dispatched) == 0


async def test_on_update_dispatches_text_message():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    update, ctx = _make_update(text="Hello bot", user_id=555, user_name="Alice")
    await adapter._on_update(update, ctx)

    assert len(dispatched) == 1
    assert dispatched[0].text == "Hello bot"
    assert dispatched[0].sender_id == "555"
    assert dispatched[0].sender_name == "Alice"
    assert dispatched[0].channel == "telegram"


async def test_on_update_sets_thread_id():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    update, ctx = _make_update(chat_id=7777)
    await adapter._on_update(update, ctx)

    assert dispatched[0].thread_id == "7777"


async def test_on_update_voice_adds_audio_attachment():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    update, ctx = _make_update(text=None, voice=True)
    await adapter._on_update(update, ctx)

    assert len(dispatched) == 1
    attach_types = [a.type for a in dispatched[0].attachments]
    assert "audio" in attach_types


async def test_on_update_voice_downloads_audio_bytes():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    update, ctx = _make_update(text=None, voice=True)
    await adapter._on_update(update, ctx)

    audio_attachment = next(a for a in dispatched[0].attachments if a.type == "audio")
    assert audio_attachment.data == b"oggdata"
    ctx.bot.get_file.assert_awaited_once_with("voice-file-id")


async def test_on_update_document_adds_attachment():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    update, ctx = _make_update(document=True)
    await adapter._on_update(update, ctx)

    assert len(dispatched) == 1
    attach_types = [a.type for a in dispatched[0].attachments]
    assert "document" in attach_types


async def test_on_update_reply_to_id_set():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    update, ctx = _make_update(reply_to_id=55)
    await adapter._on_update(update, ctx)

    assert dispatched[0].reply_to_id == "55"

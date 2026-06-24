"""Unit tests for cortexflow.channels.slack — SlackAdapter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow.channels.slack import SlackAdapter, _guess_type


def _mock_slack_bolt_modules(app_instance: MagicMock, handler_instance: MagicMock) -> dict:
    return {
        "slack_bolt": MagicMock(),
        "slack_bolt.async_app": MagicMock(AsyncApp=MagicMock(return_value=app_instance)),
        "slack_bolt.adapter": MagicMock(),
        "slack_bolt.adapter.socket_mode": MagicMock(),
        "slack_bolt.adapter.socket_mode.async_handler": MagicMock(
            AsyncSocketModeHandler=MagicMock(return_value=handler_instance)
        ),
    }


def make_adapter(**overrides) -> SlackAdapter:
    cfg = {
        "bot_token": "xoxb-test-token",
        "app_token": "xapp-test-token",
        "signing_secret": "test-secret",
        **overrides,
    }
    return SlackAdapter(cfg)


# ---------------------------------------------------------------------------
# Construction & _resolve
# ---------------------------------------------------------------------------


def test_construction_defaults():
    adapter = make_adapter()
    assert adapter.channel_id == "slack"
    assert adapter._app is None
    assert adapter._task is None
    assert adapter._bot_user_id is None


def test_construction_resolves_tokens():
    adapter = make_adapter(bot_token="xoxb-plain", app_token="xapp-plain")
    assert adapter._bot_token == "xoxb-plain"
    assert adapter._app_token == "xapp-plain"


def test_resolve_env_var(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN_TEST", "xoxb-from-env")
    adapter = SlackAdapter({"bot_token": "ENV:SLACK_BOT_TOKEN_TEST", "app_token": ""})
    assert adapter._bot_token == "xoxb-from-env"


def test_resolve_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("SLACK_NO_SUCH", raising=False)
    adapter = SlackAdapter({"bot_token": "ENV:SLACK_NO_SUCH", "app_token": ""})
    assert adapter._bot_token == ""


# ---------------------------------------------------------------------------
# get_config_schema
# ---------------------------------------------------------------------------


def test_config_schema_required_fields():
    schema = make_adapter().get_config_schema()
    assert "bot_token" in schema["required"]
    assert "app_token" in schema["required"]


def test_config_schema_has_signing_secret():
    schema = make_adapter().get_config_schema()
    assert "signing_secret" in schema["properties"]


# ---------------------------------------------------------------------------
# _guess_type
# ---------------------------------------------------------------------------


def test_guess_type_image():
    assert _guess_type("image/jpeg") == "image"


def test_guess_type_audio():
    assert _guess_type("audio/ogg") == "audio"


def test_guess_type_video():
    assert _guess_type("video/webm") == "video"


def test_guess_type_document():
    assert _guess_type("application/octet-stream") == "document"


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


async def test_send_no_app_raises():
    adapter = make_adapter()
    with pytest.raises(RuntimeError, match="not connected"):
        await adapter.send("C12345", "hello")


async def test_send_success_returns_ts():
    adapter = make_adapter()
    mock_resp = {"ts": "1234567890.000100"}
    mock_client = MagicMock()
    mock_client.chat_postMessage = AsyncMock(return_value=mock_resp)
    mock_app = MagicMock()
    mock_app.client = mock_client
    adapter._app = mock_app

    result = await adapter.send("C12345", "Hello Slack!")
    assert result == "1234567890.000100"
    mock_client.chat_postMessage.assert_called_once()


async def test_send_with_reply_to_sets_thread_ts():
    adapter = make_adapter()
    mock_client = MagicMock()
    mock_client.chat_postMessage = AsyncMock(return_value={"ts": "ts-val"})
    mock_app = MagicMock()
    mock_app.client = mock_client
    adapter._app = mock_app

    await adapter.send("C12345", "threaded reply", reply_to="1234567890.000001")
    call_kwargs = mock_client.chat_postMessage.call_args[1]
    assert call_kwargs["thread_ts"] == "1234567890.000001"


# ---------------------------------------------------------------------------
# _on_event
# ---------------------------------------------------------------------------


async def test_on_event_own_message_filtered():
    adapter = make_adapter()
    adapter._bot_user_id = "UBOT123"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._on_event({"user": "UBOT123", "text": "own msg"})
    assert len(dispatched) == 0


async def test_on_event_strips_bot_mention_prefix():
    adapter = make_adapter()
    adapter._bot_user_id = "UBOT123"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._on_event({"user": "UUSER1", "text": "<@UBOT123> hello there"})
    assert len(dispatched) == 1
    assert dispatched[0].text == "hello there"


async def test_on_event_dispatches_inbound_message():
    adapter = make_adapter()
    adapter._bot_user_id = "UBOT123"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._on_event({
        "user": "UUSER1",
        "username": "alice",
        "text": "What can you do?",
        "thread_ts": "1234.000",
    })
    assert len(dispatched) == 1
    assert dispatched[0].sender_id == "UUSER1"
    assert dispatched[0].sender_name == "alice"
    assert dispatched[0].text == "What can you do?"
    assert dispatched[0].channel == "slack"


async def test_on_event_uses_user_id_as_name_fallback():
    adapter = make_adapter()
    adapter._bot_user_id = None
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._on_event({"user": "UUSER2"})  # no username key
    assert dispatched[0].sender_name == "UUSER2"


# ---------------------------------------------------------------------------
# _on_command
# ---------------------------------------------------------------------------


async def test_on_command_dispatches_inbound_message():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._on_command({
        "command": "/reset",
        "text": "",
        "user_id": "UUSER3",
        "user_name": "bob",
    })
    assert len(dispatched) == 1
    assert dispatched[0].text == "/reset"
    assert dispatched[0].sender_id == "UUSER3"
    assert dispatched[0].sender_name == "bob"


async def test_on_command_includes_command_args():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._on_command({
        "command": "/model",
        "text": "deepseek-coder",
        "user_id": "U1",
        "user_name": "user",
    })
    assert dispatched[0].text == "/model deepseek-coder"


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


async def test_connect_raises_if_slack_bolt_not_installed():
    adapter = make_adapter()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("slack_bolt"):
            raise ImportError("No module named 'slack_bolt'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="pip install slack-bolt"):
            await adapter.connect()


async def test_connect_raises_if_no_bot_token():
    adapter = make_adapter(bot_token="")
    mock_app_instance = MagicMock()
    mock_handler_instance = MagicMock()

    with patch.dict("sys.modules", _mock_slack_bolt_modules(mock_app_instance, mock_handler_instance)):
        with pytest.raises(RuntimeError, match="bot_token"):
            await adapter.connect()


async def test_connect_raises_if_no_app_token():
    adapter = make_adapter(app_token="")
    mock_app_instance = MagicMock()
    mock_handler_instance = MagicMock()

    with patch.dict("sys.modules", _mock_slack_bolt_modules(mock_app_instance, mock_handler_instance)):
        with pytest.raises(RuntimeError, match="app_token"):
            await adapter.connect()


async def test_connect_success_resolves_bot_user_id_and_starts_task():
    adapter = make_adapter()

    mock_app_instance = MagicMock()
    mock_client = MagicMock()
    mock_client.auth_test = AsyncMock(return_value={"user_id": "UBOT999"})
    mock_app_instance.client = mock_client

    mock_handler_instance = MagicMock()
    mock_handler_instance.start_async = AsyncMock()

    with patch.dict("sys.modules", _mock_slack_bolt_modules(mock_app_instance, mock_handler_instance)):
        await adapter.connect()

    assert adapter._bot_user_id == "UBOT999"
    assert adapter._app is mock_app_instance
    assert adapter._task is not None

    await adapter.disconnect()


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


async def test_disconnect_with_no_task_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()  # should not raise


async def test_disconnect_cancels_task():
    adapter = make_adapter()

    async def _never_ending():
        await asyncio.sleep(100)

    adapter._task = asyncio.create_task(_never_ending())

    await adapter.disconnect()

    assert adapter._task is None


# ---------------------------------------------------------------------------
# _register_handlers
# ---------------------------------------------------------------------------


def _capture_handlers(adapter: SlackAdapter) -> dict:
    """Register handlers against a fake app that captures the decorated functions."""
    captured: dict = {"commands": {}}

    def fake_event(event_type):
        def decorator(fn):
            captured[event_type] = fn
            return fn
        return decorator

    def fake_command(cmd_name):
        def decorator(fn):
            captured["commands"][cmd_name] = fn
            return fn
        return decorator

    mock_app = MagicMock()
    mock_app.event = fake_event
    mock_app.command = fake_command
    adapter._app = mock_app

    adapter._register_handlers()
    return captured


async def test_register_handlers_registers_all_commands():
    adapter = make_adapter()
    captured = _capture_handlers(adapter)

    assert "app_mention" in captured
    assert "message" in captured
    assert set(captured["commands"].keys()) == {
        "/reset", "/memory", "/model", "/status", "/compact", "/voice",
    }


async def test_register_handlers_app_mention_calls_on_event():
    adapter = make_adapter()
    captured = _capture_handlers(adapter)
    events_seen = []
    adapter._on_event = lambda event: events_seen.append(event) or asyncio.sleep(0)

    await captured["app_mention"]({"user": "U1", "text": "hi"}, say=MagicMock())

    assert len(events_seen) == 1


async def test_register_handlers_message_dispatches_dm_only():
    adapter = make_adapter()
    captured = _capture_handlers(adapter)
    events_seen = []
    adapter._on_event = lambda event: events_seen.append(event) or asyncio.sleep(0)

    await captured["message"]({"channel_type": "im", "user": "U1", "text": "dm text"})
    assert len(events_seen) == 1

    await captured["message"]({"channel_type": "channel", "user": "U1", "text": "channel noise"})
    assert len(events_seen) == 1  # unchanged — not a DM

    await captured["message"]({"channel_type": "im", "user": "U1", "bot_id": "B1", "text": "bot echo"})
    assert len(events_seen) == 1  # unchanged — bot message


async def test_register_handlers_slash_command_acks_and_dispatches():
    adapter = make_adapter()
    captured = _capture_handlers(adapter)
    commands_seen = []
    adapter._on_command = lambda command: commands_seen.append(command) or asyncio.sleep(0)

    ack = AsyncMock()
    await captured["commands"]["/reset"](ack=ack, command={"command": "/reset", "user_id": "U1"})

    ack.assert_awaited_once()
    assert len(commands_seen) == 1

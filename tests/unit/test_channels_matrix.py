"""Unit tests for NeuralCleave.channels.matrix — MatrixAdapter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.matrix import MatrixAdapter


def make_adapter(**overrides) -> MatrixAdapter:
    cfg = {
        "homeserver": "https://matrix.org",
        "user_id": "@bot:matrix.org",
        "access_token": "token-abc",
        **overrides,
    }
    return MatrixAdapter(cfg)


def _mock_nio_module() -> MagicMock:
    mock_nio = MagicMock()
    mock_nio.AsyncClient = MagicMock()
    mock_nio.InviteEvent = MagicMock()
    mock_nio.RoomMessageText = MagicMock()
    return mock_nio


# ---------------------------------------------------------------------------
# Construction / resolution
# ---------------------------------------------------------------------------


def test_channel_id():
    assert make_adapter().channel_id == "matrix"


def test_defaults():
    adapter = MatrixAdapter({})
    assert adapter._homeserver == "https://matrix.org"
    assert adapter._user_id == ""
    assert adapter._device_name == "NeuralCleave"


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("MATRIX_TOKEN_TEST", "resolved-token")
    adapter = make_adapter(access_token="ENV:MATRIX_TOKEN_TEST")
    assert adapter._access_token == "resolved-token"


def test_resolve_plain_value():
    adapter = make_adapter(access_token="plain-token")
    assert adapter._access_token == "plain-token"


def test_config_schema_required_fields():
    schema = make_adapter().get_config_schema()
    assert "homeserver" in schema["required"]
    assert "user_id" in schema["required"]
    assert "access_token" in schema["required"]


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_raises_if_nio_not_installed():
    adapter = make_adapter()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "nio":
            raise ImportError("No module named 'nio'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="matrix-nio"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_success_registers_callbacks():
    adapter = make_adapter()
    mock_nio = _mock_nio_module()
    mock_client_instance = MagicMock()
    mock_client_instance.sync_forever = AsyncMock(side_effect=asyncio.CancelledError())
    mock_client_instance.close = AsyncMock()
    mock_nio.AsyncClient.return_value = mock_client_instance

    with patch.dict("sys.modules", {"nio": mock_nio}):
        await adapter.connect()
        await asyncio.sleep(0)  # let the sync task start and immediately cancel-exit

    assert adapter._client is mock_client_instance
    assert mock_client_instance.access_token == "token-abc"
    assert mock_client_instance.add_event_callback.call_count == 2

    await adapter.disconnect()


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_with_no_client_or_task_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()  # should not raise


@pytest.mark.asyncio
async def test_disconnect_cancels_sync_task_and_closes_client():
    adapter = make_adapter()
    adapter._client = MagicMock()
    adapter._client.close = AsyncMock()

    async def _never_ending():
        await asyncio.sleep(100)

    adapter._sync_task = asyncio.create_task(_never_ending())

    await adapter.disconnect()

    assert adapter._sync_task is None
    assert adapter._client is None


# ---------------------------------------------------------------------------
# send()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_client_returns_none():
    adapter = make_adapter()
    result = await adapter.send("!room:matrix.org", "hello")
    assert result is None


@pytest.mark.asyncio
async def test_send_success_returns_event_id():
    adapter = make_adapter()
    adapter._client = MagicMock()
    response = MagicMock()
    response.event_id = "$event123"
    adapter._client.room_send = AsyncMock(return_value=response)

    result = await adapter.send("!room:matrix.org", "hello")

    assert result == "$event123"
    adapter._client.room_send.assert_called_once()


@pytest.mark.asyncio
async def test_send_exception_returns_none():
    adapter = make_adapter()
    adapter._client = MagicMock()
    adapter._client.room_send = AsyncMock(side_effect=Exception("network error"))

    result = await adapter.send("!room:matrix.org", "hello")

    assert result is None


# ---------------------------------------------------------------------------
# _on_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_message_skips_own_messages():
    adapter = make_adapter()
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)
    room = MagicMock(room_id="!room:matrix.org")
    event = MagicMock(sender="@bot:matrix.org", body="hi", event_id="$1")

    await adapter._on_message(room, event)
    await asyncio.sleep(0)

    assert dispatched == []


@pytest.mark.asyncio
async def test_on_message_dispatches_other_senders():
    adapter = make_adapter()
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)
    room = MagicMock(room_id="!room:matrix.org")
    event = MagicMock(sender="@alice:matrix.org", body="hello world", event_id="$2")

    await adapter._on_message(room, event)
    await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert dispatched[0].sender_id == "@alice:matrix.org"
    assert dispatched[0].text == "hello world"
    assert dispatched[0].thread_id == "!room:matrix.org"


@pytest.mark.asyncio
async def test_on_message_no_handler_does_not_raise():
    adapter = make_adapter()
    room = MagicMock(room_id="!room:matrix.org")
    event = MagicMock(sender="@alice:matrix.org", body="hello", event_id="$3")

    await adapter._on_message(room, event)  # no handler registered


# ---------------------------------------------------------------------------
# _on_invite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_invite_no_client_is_noop():
    adapter = make_adapter()
    room = MagicMock(room_id="!room:matrix.org")
    await adapter._on_invite(room, MagicMock())  # should not raise


@pytest.mark.asyncio
async def test_on_invite_joins_room():
    adapter = make_adapter()
    adapter._client = MagicMock()
    adapter._client.join = AsyncMock()
    room = MagicMock(room_id="!room:matrix.org")

    await adapter._on_invite(room, MagicMock())

    adapter._client.join.assert_called_once_with("!room:matrix.org")


@pytest.mark.asyncio
async def test_on_invite_join_failure_does_not_raise():
    adapter = make_adapter()
    adapter._client = MagicMock()
    adapter._client.join = AsyncMock(side_effect=Exception("join failed"))
    room = MagicMock(room_id="!room:matrix.org")

    await adapter._on_invite(room, MagicMock())  # should not raise


# ---------------------------------------------------------------------------
# _sync_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_loop_no_client_returns_immediately():
    adapter = make_adapter()
    await adapter._sync_loop()  # should not raise, no client set


@pytest.mark.asyncio
async def test_sync_loop_handles_cancelled_error():
    adapter = make_adapter()
    adapter._client = MagicMock()
    adapter._client.sync_forever = AsyncMock(side_effect=asyncio.CancelledError())

    await adapter._sync_loop()  # should swallow CancelledError


@pytest.mark.asyncio
async def test_sync_loop_handles_generic_exception():
    adapter = make_adapter()
    adapter._client = MagicMock()
    adapter._client.sync_forever = AsyncMock(side_effect=Exception("sync error"))

    await adapter._sync_loop()  # should swallow and log

"""Unit tests for cortexflow.channels.nextcloud — NextcloudAdapter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.channels.nextcloud import NextcloudAdapter


def _mock_httpx_client(mock_resp) -> MagicMock:
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=mock_resp)
    client.post = AsyncMock(return_value=mock_resp)
    return client


def make_adapter(**overrides) -> NextcloudAdapter:
    cfg = {
        "url": "https://cloud.example.com",
        "username": "bot",
        "password": "app-pw",
        "room_token": "room123",
        "poll_interval": 5,
        **overrides,
    }
    return NextcloudAdapter(cfg)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construction_defaults():
    adapter = make_adapter()
    assert adapter.channel_id == "nextcloud"
    assert adapter._room_token == "room123"
    assert adapter._poll_interval == 5.0


def test_url_trailing_slash_stripped():
    adapter = make_adapter(url="https://cloud.example.com/")
    assert adapter._url == "https://cloud.example.com"


def test_construction_env_resolution(monkeypatch):
    monkeypatch.setenv("NC_USER_TEST", "resolved-user")
    adapter = NextcloudAdapter({"username": "ENV:NC_USER_TEST", "password": "pw"})
    assert adapter._username == "resolved-user"


def test_construction_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("NC_NO_SUCH", raising=False)
    adapter = NextcloudAdapter({"password": "ENV:NC_NO_SUCH"})
    assert adapter._password == ""


def test_initial_last_message_id_zero():
    adapter = make_adapter()
    assert adapter._last_message_id == 0


# ---------------------------------------------------------------------------
# get_config_schema
# ---------------------------------------------------------------------------


def test_config_schema_required_fields():
    schema = make_adapter().get_config_schema()
    for field in ("url", "username", "password", "room_token"):
        assert field in schema["required"]


# ---------------------------------------------------------------------------
# send — missing credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_credentials_returns_none():
    adapter = make_adapter(username="", password="")
    result = await adapter.send("room123", "hello")
    assert result is None


# ---------------------------------------------------------------------------
# send — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_success_returns_message_id():
    adapter = make_adapter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"ocs": {"data": {"id": 4242}}})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("room123", "Hello Talk!")

    assert result == "4242"


@pytest.mark.asyncio
async def test_send_falls_back_to_configured_room():
    adapter = make_adapter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"ocs": {"data": {"id": 1}}})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("", "uses default room")

    assert result == "1"
    # The POST URL should include the configured room token
    call = mock_client.post.call_args
    assert "room123" in call[0][0]


@pytest.mark.asyncio
async def test_send_http_error_returns_none():
    adapter = make_adapter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("500 error"))

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("room123", "hello")

    assert result is None


# ---------------------------------------------------------------------------
# _process_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_message_updates_last_id():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    await adapter._process_message({
        "id": 99,
        "actorId": "alice",
        "actorDisplayName": "Alice",
        "message": "hi bot",
        "timestamp": 123.0,
    })
    assert adapter._last_message_id == 99


@pytest.mark.asyncio
async def test_process_message_skips_system_messages():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._process_message({
        "id": 10,
        "systemMessage": "user_added",
        "messageType": "system",
        "message": "Alice joined",
    })
    assert len(dispatched) == 0


@pytest.mark.asyncio
async def test_process_message_skips_own_messages():
    adapter = make_adapter()
    adapter._own_user_id = "bot"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._process_message({
        "id": 11,
        "actorId": "bot",
        "message": "my own message",
    })
    assert len(dispatched) == 0


@pytest.mark.asyncio
async def test_process_message_dispatches_inbound():
    import asyncio

    adapter = make_adapter()
    adapter._own_user_id = "bot"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._process_message({
        "id": 12,
        "actorId": "alice",
        "actorDisplayName": "Alice",
        "message": "Hey bot!",
        "timestamp": 555.0,
    })
    await asyncio.sleep(0)  # let create_task run

    assert len(dispatched) == 1
    assert dispatched[0].text == "Hey bot!"
    assert dispatched[0].sender_id == "alice"
    assert dispatched[0].sender_name == "Alice"


@pytest.mark.asyncio
async def test_process_message_skips_empty_text():
    adapter = make_adapter()
    adapter._own_user_id = "bot"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._process_message({
        "id": 13,
        "actorId": "alice",
        "message": "   ",
    })
    assert len(dispatched) == 0


# ---------------------------------------------------------------------------
# _fetch_own_user_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_own_user_id_no_credentials():
    adapter = make_adapter(username="", password="")
    result = await adapter._fetch_own_user_id()
    assert result is None


@pytest.mark.asyncio
async def test_fetch_own_user_id_success():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"ocs": {"data": {"id": "alice"}}})

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client(mock_resp)):
        result = await adapter._fetch_own_user_id()

    assert result == "alice"


@pytest.mark.asyncio
async def test_fetch_own_user_id_http_error_returns_none():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("401"))

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client(mock_resp)):
        result = await adapter._fetch_own_user_id()

    assert result is None


# ---------------------------------------------------------------------------
# _fetch_last_message_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_last_message_id_no_room_or_credentials():
    adapter = make_adapter(room_token="", username="", password="")
    result = await adapter._fetch_last_message_id()
    assert result == 0


@pytest.mark.asyncio
async def test_fetch_last_message_id_returns_latest():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"ocs": {"data": [{"id": 7}]}})

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client(mock_resp)):
        result = await adapter._fetch_last_message_id()

    assert result == 7


@pytest.mark.asyncio
async def test_fetch_last_message_id_no_messages_returns_zero():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"ocs": {"data": []}})

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client(mock_resp)):
        result = await adapter._fetch_last_message_id()

    assert result == 0


@pytest.mark.asyncio
async def test_fetch_last_message_id_http_error_returns_zero():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("500"))

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client(mock_resp)):
        result = await adapter._fetch_last_message_id()

    assert result == 0


# ---------------------------------------------------------------------------
# connect() / disconnect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_sets_user_id_and_last_message_id_and_starts_poll_task(monkeypatch):
    adapter = make_adapter()

    async def fake_fetch_user_id():
        return "bot-id"

    async def fake_fetch_last_id():
        return 42

    monkeypatch.setattr(adapter, "_fetch_own_user_id", fake_fetch_user_id)
    monkeypatch.setattr(adapter, "_fetch_last_message_id", fake_fetch_last_id)
    monkeypatch.setattr(adapter, "_poll_loop", AsyncMock())

    await adapter.connect()

    assert adapter._own_user_id == "bot-id"
    assert adapter._last_message_id == 42
    assert adapter._poll_task is not None

    await adapter.disconnect()


@pytest.mark.asyncio
async def test_disconnect_with_no_task_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()  # should not raise


@pytest.mark.asyncio
async def test_disconnect_cancels_poll_task(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_fetch_own_user_id", AsyncMock(return_value=None))
    monkeypatch.setattr(adapter, "_fetch_last_message_id", AsyncMock(return_value=0))

    async def _never_ending():
        await asyncio.sleep(100)

    adapter._poll_task = asyncio.create_task(_never_ending())

    await adapter.disconnect()

    assert adapter._poll_task is None


# ---------------------------------------------------------------------------
# send() — reply_to
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_with_reply_to_sets_reply_id():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"ocs": {"data": {"id": 5}}})

    mock_client = _mock_httpx_client(mock_resp)
    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.send("room123", "a reply", reply_to="99")

    sent_payload = mock_client.post.call_args[1]["json"]
    assert sent_payload["replyTo"] == 99


# ---------------------------------------------------------------------------
# _poll_once
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_once_no_room_or_credentials_returns_early():
    adapter = make_adapter(room_token="", username="", password="")
    await adapter._poll_once()  # should not raise / not call httpx


@pytest.mark.asyncio
async def test_poll_once_not_modified_status_returns_early():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 304

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client(mock_resp)):
        await adapter._poll_once()  # should return without processing


@pytest.mark.asyncio
async def test_poll_once_processes_new_messages():
    adapter = make_adapter()
    adapter._own_user_id = "bot"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={
        "ocs": {"data": [{"id": 21, "actorId": "alice", "message": "hi"}]}
    })

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client(mock_resp)):
        await adapter._poll_once()
        await asyncio.sleep(0)

    assert adapter._last_message_id == 21
    assert len(dispatched) == 1


@pytest.mark.asyncio
async def test_poll_once_http_error_propagates():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("server error"))

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client(mock_resp)):
        with pytest.raises(Exception, match="server error"):
            await adapter._poll_once()


# ---------------------------------------------------------------------------
# _poll_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_loop_runs_until_cancelled(monkeypatch):
    adapter = make_adapter()
    call_count = {"n": 0}

    async def fake_poll_once():
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(adapter, "_poll_once", fake_poll_once)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await adapter._poll_loop()  # should return cleanly on CancelledError

    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_poll_loop_continues_after_generic_exception(monkeypatch):
    adapter = make_adapter()
    call_count = {"n": 0}

    async def fake_poll_once():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient error")
        raise asyncio.CancelledError()

    monkeypatch.setattr(adapter, "_poll_once", fake_poll_once)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await adapter._poll_loop()

    assert call_count["n"] == 2

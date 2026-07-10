"""Unit tests for cortexflow_ai.channels.imessage — iMessageAdapter.

Covers:
  - Construction / config parsing
  - is_connected lifecycle
  - connect() / disconnect()
  - send() — URL, payload, auth, return value, error handling
  - _process_message() — filtering, field extraction, dispatch
  - _poll_once() — URL, params, high-water mark, error handling
  - _poll_loop() — cancel safety, poll interval
  - ping() — success, failure, URL
  - get_config_schema()
  - Target format variations
  - Edge cases
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.channels.imessage import _DEFAULT_SERVER, iMessageAdapter

# ===========================================================================
# Fixtures / helpers
# ===========================================================================


def make_adapter(**overrides: Any) -> iMessageAdapter:
    cfg: dict[str, Any] = {"password": "secret", **overrides}
    return iMessageAdapter(cfg)


def make_message(
    text: str = "Hello!",
    sender_address: str = "+15551234567",
    sender_display: str = "Alice",
    is_from_me: bool = False,
    chat_guid: str = "iMessage;-;+15551234567",
    date_created: int = 1_700_000_000_000,
) -> dict[str, Any]:
    return {
        "guid": "msg-guid-001",
        "text": text,
        "isFromMe": is_from_me,
        "dateCreated": date_created,
        "handle": {
            "address": sender_address,
            "displayName": sender_display,
        },
        "chats": [{"guid": chat_guid}],
    }


def _fake_http_response(json_data: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    if status >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def _fake_client(response: MagicMock) -> MagicMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ===========================================================================
# 1. Construction / config parsing
# ===========================================================================


def test_default_server_url():
    adapter = make_adapter()
    assert adapter._server_url == _DEFAULT_SERVER


def test_default_server_url_constant():
    assert _DEFAULT_SERVER == "http://localhost:1234"


def test_custom_server_url():
    adapter = make_adapter(server_url="http://192.168.1.10:1234")
    assert adapter._server_url == "http://192.168.1.10:1234"


def test_trailing_slash_stripped():
    adapter = make_adapter(server_url="http://192.168.1.10:1234/")
    assert adapter._server_url == "http://192.168.1.10:1234"


def test_double_trailing_slash_stripped():
    adapter = make_adapter(server_url="http://host:1234//")
    assert adapter._server_url == "http://host:1234"


def test_password_stored():
    adapter = make_adapter(password="my-secret")
    assert adapter._password == "my-secret"


def test_empty_password_allowed():
    adapter = make_adapter(password="")
    assert adapter._password == ""


def test_default_poll_interval():
    adapter = make_adapter()
    assert adapter._poll_interval == 5.0


def test_custom_poll_interval():
    adapter = make_adapter(poll_interval=2.5)
    assert adapter._poll_interval == 2.5


def test_poll_interval_string_coerced():
    adapter = make_adapter(poll_interval="3")
    assert adapter._poll_interval == 3.0


def test_default_method():
    adapter = make_adapter()
    assert adapter._method == "apple-script"


def test_private_api_method():
    adapter = make_adapter(method="private-api")
    assert adapter._method == "private-api"


def test_default_bot_handle_empty():
    adapter = make_adapter()
    assert adapter._bot_handle == ""


def test_custom_bot_handle():
    adapter = make_adapter(bot_handle="user@icloud.com")
    assert adapter._bot_handle == "user@icloud.com"


def test_poll_task_starts_none():
    adapter = make_adapter()
    assert adapter._poll_task is None


def test_after_ms_starts_zero():
    adapter = make_adapter()
    assert adapter._after_ms == 0


def test_channel_id():
    adapter = make_adapter()
    assert adapter.channel_id == "imessage"


# ===========================================================================
# 2. is_connected (via base class _poll_task check)
# ===========================================================================


def test_not_connected_initially():
    adapter = make_adapter()
    assert adapter.is_connected is False


@pytest.mark.asyncio
async def test_connected_after_connect():
    adapter = make_adapter()
    with patch("asyncio.create_task") as mock_task:
        mock_task.return_value = MagicMock()
        await adapter.connect()
        assert adapter._poll_task is not None


@pytest.mark.asyncio
async def test_is_connected_true_after_connect():
    adapter = make_adapter()
    task_mock = MagicMock()
    task_mock.done = MagicMock(return_value=False)
    with patch("asyncio.create_task", return_value=task_mock):
        await adapter.connect()
    assert adapter.is_connected is True


@pytest.mark.asyncio
async def test_not_connected_after_disconnect():
    adapter = make_adapter()
    task_mock = MagicMock()
    task_mock.done = MagicMock(return_value=False)
    task_mock.cancel = MagicMock()
    # Make await work
    async def _await_task():
        raise asyncio.CancelledError()
    task_mock.__await__ = lambda self: _await_task().__await__()

    with patch("asyncio.create_task", return_value=task_mock):
        await adapter.connect()

    adapter._poll_task = None  # simulate cancelled
    assert adapter.is_connected is False


@pytest.mark.asyncio
async def test_poll_task_none_after_disconnect():
    adapter = make_adapter()

    async def _fake_poll_loop():
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            raise

    await adapter.connect()
    assert adapter._poll_task is not None
    await adapter.disconnect()
    assert adapter._poll_task is None


# ===========================================================================
# 3. connect() / disconnect()
# ===========================================================================


@pytest.mark.asyncio
async def test_connect_sets_after_ms():
    adapter = make_adapter()
    before = int(time.time() * 1000) - 100
    await adapter.connect()
    after = int(time.time() * 1000) + 100
    await adapter.disconnect()
    assert before < adapter._after_ms < after


@pytest.mark.asyncio
async def test_connect_creates_poll_task():
    adapter = make_adapter()
    await adapter.connect()
    assert adapter._poll_task is not None
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_disconnect_cancels_poll_task():
    adapter = make_adapter()
    await adapter.connect()
    task = adapter._poll_task
    await adapter.disconnect()
    assert task.cancelled()


@pytest.mark.asyncio
async def test_disconnect_sets_poll_task_none():
    adapter = make_adapter()
    await adapter.connect()
    await adapter.disconnect()
    assert adapter._poll_task is None


@pytest.mark.asyncio
async def test_disconnect_when_not_connected_is_safe():
    adapter = make_adapter()
    await adapter.disconnect()  # must not raise
    assert adapter._poll_task is None


@pytest.mark.asyncio
async def test_connect_disconnect_cycle():
    adapter = make_adapter()
    await adapter.connect()
    await adapter.disconnect()
    await adapter.connect()
    await adapter.disconnect()
    assert adapter._poll_task is None


@pytest.mark.asyncio
async def test_after_ms_not_reset_on_disconnect():
    adapter = make_adapter()
    await adapter.connect()
    saved = adapter._after_ms
    await adapter.disconnect()
    assert adapter._after_ms == saved


# ===========================================================================
# 4. send()
# ===========================================================================


@pytest.mark.asyncio
async def test_send_posts_to_correct_url():
    adapter = make_adapter()
    resp = _fake_http_response({"data": {"guid": "msg-001"}})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.send("iMessage;-;+15551234567", "Hello")

    call_args = client.post.call_args
    assert "/api/v1/message/text" in call_args[0][0]


@pytest.mark.asyncio
async def test_send_includes_server_url():
    adapter = make_adapter(server_url="http://myserver:9999")
    resp = _fake_http_response({"data": {"guid": "x"}})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.send("iMessage;-;+1555", "Hi")

    url = client.post.call_args[0][0]
    assert url.startswith("http://myserver:9999")


@pytest.mark.asyncio
async def test_send_chat_guid_in_body():
    adapter = make_adapter()
    resp = _fake_http_response({"data": {"guid": "g"}})
    client = _fake_client(resp)
    target = "iMessage;-;+15551234567"

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.send(target, "Hi")

    body = client.post.call_args[1]["json"]
    assert body["chatGuid"] == target


@pytest.mark.asyncio
async def test_send_message_in_body():
    adapter = make_adapter()
    resp = _fake_http_response({"data": {"guid": "g"}})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.send("iMessage;-;+1555", "Test message")

    body = client.post.call_args[1]["json"]
    assert body["message"] == "Test message"


@pytest.mark.asyncio
async def test_send_method_in_body():
    adapter = make_adapter(method="private-api")
    resp = _fake_http_response({"data": {"guid": "g"}})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.send("iMessage;-;+1555", "Hi")

    body = client.post.call_args[1]["json"]
    assert body["method"] == "private-api"


@pytest.mark.asyncio
async def test_send_default_method_apple_script():
    adapter = make_adapter()
    resp = _fake_http_response({"data": {"guid": "g"}})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.send("iMessage;-;+1555", "Hi")

    body = client.post.call_args[1]["json"]
    assert body["method"] == "apple-script"


@pytest.mark.asyncio
async def test_send_password_in_params():
    adapter = make_adapter(password="topsecret")
    resp = _fake_http_response({"data": {"guid": "g"}})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.send("iMessage;-;+1555", "Hi")

    params = client.post.call_args[1]["params"]
    assert params["password"] == "topsecret"


@pytest.mark.asyncio
async def test_send_returns_guid_on_success():
    adapter = make_adapter()
    resp = _fake_http_response({"data": {"guid": "msg-abc-123"}})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        result = await adapter.send("iMessage;-;+1555", "Hi")

    assert result == "msg-abc-123"


@pytest.mark.asyncio
async def test_send_returns_none_on_http_error():
    adapter = make_adapter()
    resp = _fake_http_response({}, status=500)
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        result = await adapter.send("iMessage;-;+1555", "Hi")

    assert result is None


@pytest.mark.asyncio
async def test_send_returns_none_on_4xx():
    adapter = make_adapter()
    resp = _fake_http_response({}, status=401)
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        result = await adapter.send("iMessage;-;+1555", "Hi")

    assert result is None


@pytest.mark.asyncio
async def test_send_returns_none_on_network_error():
    adapter = make_adapter()
    import httpx
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("httpx.AsyncClient", return_value=client):
        result = await adapter.send("iMessage;-;+1555", "Hi")

    assert result is None


@pytest.mark.asyncio
async def test_send_returns_none_when_data_missing():
    adapter = make_adapter()
    resp = _fake_http_response({"status": 200})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        result = await adapter.send("iMessage;-;+1555", "Hi")

    assert result is None


@pytest.mark.asyncio
async def test_send_returns_none_when_guid_missing():
    adapter = make_adapter()
    resp = _fake_http_response({"data": {}})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        result = await adapter.send("iMessage;-;+1555", "Hi")

    assert result is None


@pytest.mark.asyncio
async def test_send_imessage_email_target():
    adapter = make_adapter()
    resp = _fake_http_response({"data": {"guid": "g"}})
    client = _fake_client(resp)
    target = "iMessage;-;user@example.com"

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.send(target, "Hello")

    body = client.post.call_args[1]["json"]
    assert body["chatGuid"] == target


@pytest.mark.asyncio
async def test_send_sms_target():
    adapter = make_adapter()
    resp = _fake_http_response({"data": {"guid": "g"}})
    client = _fake_client(resp)
    target = "SMS;-;+15551234567"

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.send(target, "SMS message")

    body = client.post.call_args[1]["json"]
    assert body["chatGuid"] == target


@pytest.mark.asyncio
async def test_send_group_chat_target():
    adapter = make_adapter()
    resp = _fake_http_response({"data": {"guid": "g"}})
    client = _fake_client(resp)
    target = "iMessage;+;chat-group-abc"

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.send(target, "Group message")

    body = client.post.call_args[1]["json"]
    assert body["chatGuid"] == target


@pytest.mark.asyncio
async def test_send_timeout_is_15():
    adapter = make_adapter()
    resp = _fake_http_response({"data": {"guid": "g"}})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.send("iMessage;-;+1555", "Hi")

    call_kwargs = client.post.call_args[1]
    assert call_kwargs["timeout"] == 15.0


# ===========================================================================
# 5. _process_message()
# ===========================================================================


@pytest.mark.asyncio
async def test_process_skips_is_from_me():
    adapter = make_adapter()
    dispatched = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(is_from_me=True)
    await adapter._process_message(msg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_process_skips_empty_text():
    adapter = make_adapter()
    dispatched = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(text="")
    msg["isFromMe"] = False
    await adapter._process_message(msg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_process_skips_whitespace_only_text():
    adapter = make_adapter()
    dispatched = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(text="   ")
    await adapter._process_message(msg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_process_dispatches_valid_message():
    adapter = make_adapter()
    dispatched = []

    async def _handler(m):
        dispatched.append(m)

    adapter._handler = _handler
    msg = make_message(text="Hello")

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert dispatched[0].text == "Hello"


@pytest.mark.asyncio
async def test_process_extracts_sender_id():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(sender_address="+15559876543")

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert dispatched[0].sender_id == "+15559876543"


@pytest.mark.asyncio
async def test_process_extracts_sender_name():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(sender_display="Bob Smith")

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert dispatched[0].sender_name == "Bob Smith"


@pytest.mark.asyncio
async def test_process_falls_back_to_address_for_name():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(sender_address="+1555", sender_display="")
    msg["handle"]["displayName"] = ""

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert dispatched[0].sender_name == "+1555"


@pytest.mark.asyncio
async def test_process_uses_unknown_when_no_handle():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message()
    msg["handle"] = None

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert dispatched[0].sender_id == "unknown"


@pytest.mark.asyncio
async def test_process_extracts_chat_guid_from_chats():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(chat_guid="iMessage;+;group-abc")

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert dispatched[0].thread_id == "iMessage;+;group-abc"


@pytest.mark.asyncio
async def test_process_falls_back_to_sender_when_no_chats():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(sender_address="+1555")
    msg["chats"] = []

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert dispatched[0].thread_id == "+1555"


@pytest.mark.asyncio
async def test_process_falls_back_to_sender_when_chats_none():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(sender_address="+1555")
    msg["chats"] = None

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert dispatched[0].thread_id == "+1555"


@pytest.mark.asyncio
async def test_process_skips_own_handle():
    adapter = make_adapter(bot_handle="+1555")
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(sender_address="+1555")

    await adapter._process_message(msg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_process_does_not_skip_different_handle():
    adapter = make_adapter(bot_handle="+1555")
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(sender_address="+19991234567")

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert len(dispatched) == 1


@pytest.mark.asyncio
async def test_process_no_bot_handle_does_not_filter():
    adapter = make_adapter(bot_handle="")
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(sender_address="+1555")

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert len(dispatched) == 1


@pytest.mark.asyncio
async def test_process_raw_contains_original_data():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(text="Raw test")

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert dispatched[0].raw is msg


@pytest.mark.asyncio
async def test_process_channel_is_imessage():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message(text="Channel test")

    with patch("asyncio.create_task") as mock_ct:
        mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
        await adapter._process_message(msg)
        await asyncio.sleep(0)

    assert dispatched[0].channel == "imessage"


@pytest.mark.asyncio
async def test_process_no_text_key():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message()
    del msg["text"]
    await adapter._process_message(msg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_process_none_text():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))
    msg = make_message()
    msg["text"] = None
    await adapter._process_message(msg)
    assert dispatched == []


# ===========================================================================
# 6. _poll_once()
# ===========================================================================


@pytest.mark.asyncio
async def test_poll_once_gets_correct_url():
    adapter = make_adapter(server_url="http://myhost:1234")
    resp = _fake_http_response({"data": []})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter._poll_once()

    url = client.get.call_args[0][0]
    assert "myhost:1234" in url
    assert "/api/v1/message" in url


@pytest.mark.asyncio
async def test_poll_once_passes_password():
    adapter = make_adapter(password="pw123")
    resp = _fake_http_response({"data": []})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter._poll_once()

    params = client.get.call_args[1]["params"]
    assert params["password"] == "pw123"


@pytest.mark.asyncio
async def test_poll_once_passes_limit():
    adapter = make_adapter()
    resp = _fake_http_response({"data": []})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter._poll_once()

    params = client.get.call_args[1]["params"]
    assert params["limit"] == 50


@pytest.mark.asyncio
async def test_poll_once_passes_after_ms():
    adapter = make_adapter()
    adapter._after_ms = 1_700_000_000_000
    resp = _fake_http_response({"data": []})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter._poll_once()

    params = client.get.call_args[1]["params"]
    assert params["after"] == 1_700_000_000_000


@pytest.mark.asyncio
async def test_poll_once_passes_sort_date():
    adapter = make_adapter()
    resp = _fake_http_response({"data": []})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter._poll_once()

    params = client.get.call_args[1]["params"]
    assert params["sort"] == "date"


@pytest.mark.asyncio
async def test_poll_once_processes_messages():
    adapter = make_adapter()
    dispatched: list = []
    adapter._handler = AsyncMock(side_effect=lambda m: dispatched.append(m))

    msg = make_message(text="Polled message", date_created=1_700_000_000_500)
    resp = _fake_http_response({"data": [msg]})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        with patch("asyncio.create_task") as mock_ct:
            mock_ct.side_effect = lambda coro: asyncio.ensure_future(coro)
            await adapter._poll_once()
            await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert dispatched[0].text == "Polled message"


@pytest.mark.asyncio
async def test_poll_once_updates_after_ms():
    adapter = make_adapter()
    adapter._after_ms = 1_000
    msg = make_message(date_created=1_700_000_000_999)
    resp = _fake_http_response({"data": [msg]})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        with patch("asyncio.create_task"):
            await adapter._poll_once()

    assert adapter._after_ms == 1_700_000_000_999


@pytest.mark.asyncio
async def test_poll_once_does_not_decrease_after_ms():
    adapter = make_adapter()
    adapter._after_ms = 9_999_999_999_999
    msg = make_message(date_created=1_000)
    resp = _fake_http_response({"data": [msg]})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        with patch("asyncio.create_task"):
            await adapter._poll_once()

    assert adapter._after_ms == 9_999_999_999_999


@pytest.mark.asyncio
async def test_poll_once_handles_http_error():
    adapter = make_adapter()
    resp = _fake_http_response({}, status=500)
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter._poll_once()  # must not raise


@pytest.mark.asyncio
async def test_poll_once_handles_network_error():
    adapter = make_adapter()
    import httpx
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("httpx.AsyncClient", return_value=client):
        await adapter._poll_once()  # must not raise


@pytest.mark.asyncio
async def test_poll_once_handles_empty_data():
    adapter = make_adapter()
    resp = _fake_http_response({"data": []})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter._poll_once()  # no messages, no crash


@pytest.mark.asyncio
async def test_poll_once_handles_missing_data_key():
    adapter = make_adapter()
    resp = _fake_http_response({})
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter._poll_once()  # must not raise


# ===========================================================================
# 7. _poll_loop()
# ===========================================================================


@pytest.mark.asyncio
async def test_poll_loop_cancels_cleanly():
    adapter = make_adapter(poll_interval=0.01)

    async def _fake_poll_once():
        pass

    adapter._poll_once = AsyncMock(side_effect=_fake_poll_once)

    task = asyncio.create_task(adapter._poll_loop())
    await asyncio.sleep(0.05)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_poll_loop_calls_poll_once():
    adapter = make_adapter(poll_interval=0.01)
    call_count = 0

    async def _counting_poll():
        nonlocal call_count
        call_count += 1

    adapter._poll_once = _counting_poll

    task = asyncio.create_task(adapter._poll_loop())
    await asyncio.sleep(0.08)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert call_count >= 1


@pytest.mark.asyncio
async def test_poll_loop_survives_exceptions():
    adapter = make_adapter(poll_interval=0.01)
    call_count = 0

    async def _failing_poll():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("temporary error")

    adapter._poll_once = _failing_poll

    task = asyncio.create_task(adapter._poll_loop())
    await asyncio.sleep(0.08)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert call_count >= 3


# ===========================================================================
# 8. ping()
# ===========================================================================


@pytest.mark.asyncio
async def test_ping_returns_true_on_200():
    adapter = make_adapter()
    resp = _fake_http_response({"message": "pong"}, status=200)
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        result = await adapter.ping()

    assert result is True


@pytest.mark.asyncio
async def test_ping_returns_false_on_4xx():
    adapter = make_adapter()
    resp = MagicMock()
    resp.status_code = 401
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        result = await adapter.ping()

    assert result is False


@pytest.mark.asyncio
async def test_ping_returns_false_on_network_error():
    adapter = make_adapter()
    import httpx
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("httpx.AsyncClient", return_value=client):
        result = await adapter.ping()

    assert result is False


@pytest.mark.asyncio
async def test_ping_uses_correct_url():
    adapter = make_adapter(server_url="http://pinghost:1234")
    resp = MagicMock()
    resp.status_code = 200
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.ping()

    url = client.get.call_args[0][0]
    assert "pinghost:1234" in url
    assert "/ping" in url


@pytest.mark.asyncio
async def test_ping_passes_password():
    adapter = make_adapter(password="pingsecret")
    resp = MagicMock()
    resp.status_code = 200
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.ping()

    params = client.get.call_args[1]["params"]
    assert params["password"] == "pingsecret"


@pytest.mark.asyncio
async def test_ping_timeout_is_5():
    adapter = make_adapter()
    resp = MagicMock()
    resp.status_code = 200
    client = _fake_client(resp)

    with patch("httpx.AsyncClient", return_value=client):
        await adapter.ping()

    call_kwargs = client.get.call_args[1]
    assert call_kwargs["timeout"] == 5.0


# ===========================================================================
# 9. get_config_schema()
# ===========================================================================


def test_schema_type_object():
    adapter = make_adapter()
    schema = adapter.get_config_schema()
    assert schema["type"] == "object"


def test_schema_password_required():
    adapter = make_adapter()
    schema = adapter.get_config_schema()
    assert "password" in schema["required"]


def test_schema_has_server_url():
    adapter = make_adapter()
    schema = adapter.get_config_schema()
    assert "server_url" in schema["properties"]


def test_schema_server_url_default():
    adapter = make_adapter()
    schema = adapter.get_config_schema()
    assert schema["properties"]["server_url"]["default"] == _DEFAULT_SERVER


def test_schema_has_poll_interval():
    adapter = make_adapter()
    schema = adapter.get_config_schema()
    assert "poll_interval" in schema["properties"]


def test_schema_poll_interval_default():
    adapter = make_adapter()
    schema = adapter.get_config_schema()
    assert schema["properties"]["poll_interval"]["default"] == 5.0


def test_schema_method_enum():
    adapter = make_adapter()
    schema = adapter.get_config_schema()
    enum = schema["properties"]["method"]["enum"]
    assert "apple-script" in enum
    assert "private-api" in enum


def test_schema_method_default():
    adapter = make_adapter()
    schema = adapter.get_config_schema()
    assert schema["properties"]["method"]["default"] == "apple-script"


def test_schema_has_bot_handle():
    adapter = make_adapter()
    schema = adapter.get_config_schema()
    assert "bot_handle" in schema["properties"]


def test_schema_has_password_property():
    adapter = make_adapter()
    schema = adapter.get_config_schema()
    assert "password" in schema["properties"]


# ===========================================================================
# 10. repr and channel_id
# ===========================================================================


def test_repr_contains_channel_id():
    adapter = make_adapter()
    assert "imessage" in repr(adapter)


def test_channel_id_class_attribute():
    assert iMessageAdapter.channel_id == "imessage"


def test_is_subclass_of_channel_adapter():
    from cortexflow_ai.channels.base import ChannelAdapter
    assert issubclass(iMessageAdapter, ChannelAdapter)

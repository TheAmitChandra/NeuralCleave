"""Unit tests for NeuralCleave.channels.xmpp — XMPPAdapter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.xmpp import XMPPAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_adapter(**overrides) -> XMPPAdapter:
    cfg = {
        "jid": "bot@jabber.org",
        "password": "xmpp-password",
        **overrides,
    }
    return XMPPAdapter(cfg)


def _mock_slixmpp_module():
    mod = MagicMock()
    client = MagicMock()
    client.is_connected.return_value = True
    client.plugin = MagicMock()
    client.plugin.get.return_value = None  # no ping plugin by default
    mod.ClientXMPP.return_value = client
    return mod, client


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_channel_id():
    assert make_adapter().channel_id == "xmpp"


def test_defaults():
    a = XMPPAdapter({})
    assert a._jid == ""
    assert a._password == ""
    assert a._server == ""
    assert a._port == 5222
    assert a._use_ssl is False
    assert a._rooms == []
    assert a._room_nick == "NeuralCleave"
    assert a._client is None


def test_custom_port():
    a = make_adapter(port=5223)
    assert a._port == 5223


def test_custom_rooms():
    a = make_adapter(rooms=["room1@conf.server", "room2@conf.server"])
    assert a._rooms == ["room1@conf.server", "room2@conf.server"]


def test_custom_room_nick():
    a = make_adapter(room_nick="mybot")
    assert a._room_nick == "mybot"


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("XMPP_PASS_TEST", "resolved-pw")
    a = make_adapter(password="ENV:XMPP_PASS_TEST")
    assert a._password == "resolved-pw"


def test_resolve_env_missing(monkeypatch):
    monkeypatch.delenv("XMPP_MISSING", raising=False)
    a = make_adapter(password="ENV:XMPP_MISSING")
    assert a._password == ""


def test_resolve_plain_string_unchanged():
    a = make_adapter(password="plaintext")
    assert a._password == "plaintext"


def test_use_ssl_flag():
    a = make_adapter(use_ssl=True)
    assert a._use_ssl is True


# ---------------------------------------------------------------------------
# Config schema
# ---------------------------------------------------------------------------


def test_config_schema_required():
    schema = make_adapter().get_config_schema()
    assert "jid" in schema["required"]
    assert "password" in schema["required"]


def test_config_schema_optional():
    schema = make_adapter().get_config_schema()
    props = schema["properties"]
    assert "server" in props
    assert "port" in props
    assert "use_ssl" in props
    assert "rooms" in props
    assert "room_nick" in props


# ---------------------------------------------------------------------------
# connect() — import guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_raises_if_slixmpp_not_installed():
    adapter = make_adapter()
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "slixmpp":
            raise ImportError("no slixmpp")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="slixmpp"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_raises_missing_jid():
    adapter = XMPPAdapter({"password": "pw"})
    mod, client = _mock_slixmpp_module()
    with patch.dict("sys.modules", {"slixmpp": mod}):
        with pytest.raises(RuntimeError, match="jid"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_raises_missing_password():
    adapter = XMPPAdapter({"jid": "bot@jabber.org"})
    mod, client = _mock_slixmpp_module()
    with patch.dict("sys.modules", {"slixmpp": mod}):
        with pytest.raises(RuntimeError, match="password"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_registers_plugins():
    adapter = make_adapter()
    mod, mock_client = _mock_slixmpp_module()

    registered_plugins = []
    mock_client.register_plugin = lambda p: registered_plugins.append(p)

    async def _resolve_future():
        await asyncio.sleep(0)
        future = adapter._connect_future
        if future and not future.done():
            future.set_result(True)

    asyncio.create_task(_resolve_future())

    with patch.dict("sys.modules", {"slixmpp": mod}):
        await adapter.connect()

    assert "xep_0030" in registered_plugins
    assert "xep_0045" in registered_plugins
    assert "xep_0199" in registered_plugins
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_connect_stores_client():
    adapter = make_adapter()
    mod, mock_client = _mock_slixmpp_module()

    async def _resolve_future():
        await asyncio.sleep(0)
        future = adapter._connect_future
        if future and not future.done():
            future.set_result(True)

    asyncio.create_task(_resolve_future())

    with patch.dict("sys.modules", {"slixmpp": mod}):
        await adapter.connect()

    assert adapter._client is mock_client
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_connect_uses_server_override():
    adapter = make_adapter(server="custom.jabber.org", port=5222)
    mod, mock_client = _mock_slixmpp_module()

    connect_calls = []
    mock_client.connect = lambda *args, **kwargs: connect_calls.append((args, kwargs))

    async def _resolve_future():
        await asyncio.sleep(0)
        future = adapter._connect_future
        if future and not future.done():
            future.set_result(True)

    asyncio.create_task(_resolve_future())

    with patch.dict("sys.modules", {"slixmpp": mod}):
        await adapter.connect()

    assert any("custom.jabber.org" in str(c) for c in connect_calls)
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_connect_timeout_raises():
    adapter = make_adapter()
    mod, mock_client = _mock_slixmpp_module()

    async def fake_wait_for(coro, timeout):
        raise asyncio.TimeoutError()

    with patch.dict("sys.modules", {"slixmpp": mod}):
        with patch("asyncio.wait_for", fake_wait_for):
            with pytest.raises(RuntimeError, match="timed out"):
                await adapter.connect()


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_without_connect_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()
    assert adapter._client is None


@pytest.mark.asyncio
async def test_disconnect_calls_client_disconnect():
    adapter = make_adapter()
    mock_client = MagicMock()
    adapter._client = mock_client
    await adapter.disconnect()
    mock_client.disconnect.assert_called_once()
    assert adapter._client is None


# ---------------------------------------------------------------------------
# is_connected (via _client attribute)
# ---------------------------------------------------------------------------


def test_is_connected_true_when_client_present():
    adapter = make_adapter()
    adapter._client = MagicMock()
    assert adapter.is_connected is True


def test_is_connected_false_when_no_client():
    adapter = make_adapter()
    assert adapter.is_connected is False


# ---------------------------------------------------------------------------
# send()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_client_returns_none():
    adapter = make_adapter()
    result = await adapter.send("user@jabber.org", "hello")
    assert result is None


@pytest.mark.asyncio
async def test_send_1to1_uses_chat_type():
    adapter = make_adapter()
    mock_client = MagicMock()
    adapter._client = mock_client
    await adapter.send("user@jabber.org", "hello")
    mock_client.send_message.assert_called_once()
    call_kwargs = mock_client.send_message.call_args
    assert call_kwargs.kwargs.get("mtype") == "chat" or call_kwargs[1].get("mtype") == "chat"


@pytest.mark.asyncio
async def test_send_muc_uses_groupchat_type():
    adapter = make_adapter()
    mock_client = MagicMock()
    adapter._client = mock_client
    await adapter.send("room@conference.jabber.org", "hello everyone")
    mock_client.send_message.assert_called_once()
    call_kwargs = mock_client.send_message.call_args
    mtype = call_kwargs.kwargs.get("mtype") or call_kwargs[1].get("mtype")
    assert mtype == "groupchat"


@pytest.mark.asyncio
async def test_send_always_returns_none():
    adapter = make_adapter()
    mock_client = MagicMock()
    adapter._client = mock_client
    result = await adapter.send("user@jabber.org", "hello")
    assert result is None


@pytest.mark.asyncio
async def test_send_exception_returns_none():
    adapter = make_adapter()
    mock_client = MagicMock()
    mock_client.send_message = MagicMock(side_effect=Exception("send failed"))
    adapter._client = mock_client
    result = await adapter.send("user@jabber.org", "hello")
    assert result is None


# ---------------------------------------------------------------------------
# ping()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ping_no_client_returns_false():
    adapter = make_adapter()
    assert await adapter.ping() is False


@pytest.mark.asyncio
async def test_ping_with_client_no_ping_plugin_returns_connected():
    adapter = make_adapter()
    mock_client = MagicMock()
    mock_client.plugin.get.return_value = None
    mock_client.is_connected.return_value = True
    adapter._client = mock_client
    result = await adapter.ping()
    assert result is True


@pytest.mark.asyncio
async def test_ping_exception_with_not_connected_returns_false():
    adapter = make_adapter()
    mock_client = MagicMock()
    mock_plugin = MagicMock()
    mock_plugin.ping = MagicMock(side_effect=Exception("ping failed"))
    mock_client.plugin.get.return_value = mock_plugin
    mock_client.is_connected.return_value = False
    adapter._client = mock_client
    result = await adapter.ping()
    assert result is False


@pytest.mark.asyncio
async def test_ping_exception_falls_back_to_is_connected():
    adapter = make_adapter()
    mock_client = MagicMock()
    mock_plugin = MagicMock()
    mock_plugin.ping = MagicMock(side_effect=Exception("ping failed"))
    mock_client.plugin.get.return_value = mock_plugin
    mock_client.is_connected.return_value = True
    adapter._client = mock_client
    result = await adapter.ping()
    assert result is True


# ---------------------------------------------------------------------------
# _on_session_start()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_session_start_resolves_connect_future():
    adapter = make_adapter()
    future = asyncio.get_event_loop().create_future()
    adapter._connect_future = future
    mock_client = MagicMock()
    mock_client.get_roster = AsyncMock()
    mock_client.plugin.get.return_value = None
    adapter._client = mock_client
    await adapter._on_session_start({})
    assert future.done()
    assert future.result() is True


@pytest.mark.asyncio
async def test_on_session_start_joins_rooms():
    adapter = make_adapter(rooms=["room1@conf.jabber.org", "room2@conf.jabber.org"])
    future = asyncio.get_event_loop().create_future()
    adapter._connect_future = future
    mock_client = MagicMock()
    mock_client.get_roster = AsyncMock()
    mock_muc = MagicMock()
    mock_client.plugin.get.return_value = mock_muc
    adapter._client = mock_client
    await adapter._on_session_start({})
    assert mock_muc.join_muc.call_count == 2


@pytest.mark.asyncio
async def test_on_session_start_no_future_does_not_raise():
    adapter = make_adapter()
    adapter._connect_future = None
    mock_client = MagicMock()
    mock_client.get_roster = AsyncMock()
    mock_client.plugin.get.return_value = None
    adapter._client = mock_client
    await adapter._on_session_start({})  # should not raise


@pytest.mark.asyncio
async def test_on_session_start_already_done_future_not_set_again():
    adapter = make_adapter()
    future = asyncio.get_event_loop().create_future()
    future.set_result(True)
    adapter._connect_future = future
    mock_client = MagicMock()
    mock_client.get_roster = AsyncMock()
    mock_client.plugin.get.return_value = None
    adapter._client = mock_client
    await adapter._on_session_start({})  # should not raise InvalidStateError


# ---------------------------------------------------------------------------
# _on_message() — 1:1 chat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_message_dispatches_chat_message():
    adapter = make_adapter()
    adapter._jid = "bot@jabber.org"
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    msg = MagicMock()
    msg.get = lambda key, default="": {
        "type": "chat",
        "body": "hello bot",
        "from": "alice@jabber.org/mobile",
    }.get(key, default)

    await adapter._on_message(msg)
    assert len(dispatched) == 1
    assert dispatched[0].text == "hello bot"
    assert dispatched[0].sender_id == "alice@jabber.org"
    assert dispatched[0].channel == "xmpp"


@pytest.mark.asyncio
async def test_on_message_ignores_non_chat_type():
    adapter = make_adapter()
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    msg = MagicMock()
    msg.get = lambda key, default="": {
        "type": "error",
        "body": "error body",
        "from": "alice@jabber.org",
    }.get(key, default)

    await adapter._on_message(msg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_on_message_ignores_empty_body():
    adapter = make_adapter()
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    msg = MagicMock()
    msg.get = lambda key, default="": {
        "type": "chat",
        "body": "",
        "from": "alice@jabber.org",
    }.get(key, default)

    await adapter._on_message(msg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_on_message_echo_guard_skips_own_jid():
    adapter = make_adapter()
    adapter._jid = "bot@jabber.org"
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    msg = MagicMock()
    msg.get = lambda key, default="": {
        "type": "chat",
        "body": "my own message",
        "from": "bot@jabber.org/resource",
    }.get(key, default)

    await adapter._on_message(msg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_on_message_sender_name_from_localpart():
    adapter = make_adapter()
    adapter._jid = "bot@jabber.org"
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    msg = MagicMock()
    msg.get = lambda key, default="": {
        "type": "chat",
        "body": "hi",
        "from": "alice@jabber.org",
    }.get(key, default)

    await adapter._on_message(msg)
    assert dispatched[0].sender_name == "alice"


# ---------------------------------------------------------------------------
# _on_groupchat_message()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_groupchat_message_dispatches():
    adapter = make_adapter(room_nick="mybot")
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    msg = MagicMock()
    msg.get = lambda key, default="": {
        "body": "group message",
        "from": "room@conference.jabber.org/alice",
    }.get(key, default)

    await adapter._on_groupchat_message(msg)
    assert len(dispatched) == 1
    assert dispatched[0].text == "group message"
    assert dispatched[0].thread_id == "room@conference.jabber.org"
    assert dispatched[0].sender_name == "alice"


@pytest.mark.asyncio
async def test_on_groupchat_message_echo_guard():
    adapter = make_adapter(room_nick="mybot")
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    msg = MagicMock()
    msg.get = lambda key, default="": {
        "body": "bot's own message",
        "from": "room@conference.jabber.org/mybot",
    }.get(key, default)

    await adapter._on_groupchat_message(msg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_on_groupchat_message_ignores_empty_body():
    adapter = make_adapter(room_nick="mybot")
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    msg = MagicMock()
    msg.get = lambda key, default="": {
        "body": "",
        "from": "room@conference.jabber.org/alice",
    }.get(key, default)

    await adapter._on_groupchat_message(msg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_on_groupchat_message_no_nick_in_from():
    adapter = make_adapter(room_nick="mybot")
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    msg = MagicMock()
    msg.get = lambda key, default="": {
        "body": "server message",
        "from": "room@conference.jabber.org",
    }.get(key, default)

    await adapter._on_groupchat_message(msg)
    assert len(dispatched) == 1
    assert dispatched[0].sender_name == "room@conference.jabber.org"


# ---------------------------------------------------------------------------
# _on_disconnected() and _on_failed_auth()
# ---------------------------------------------------------------------------


def test_on_disconnected_does_not_raise():
    adapter = make_adapter()
    adapter._on_disconnected({})  # should log and return without raising


def test_on_failed_auth_sets_future_exception():
    adapter = make_adapter()
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        adapter._connect_future = future
        adapter._on_failed_auth({})
        assert future.done()
        assert isinstance(future.exception(), RuntimeError)
        assert "authentication failed" in str(future.exception()).lower()
    finally:
        loop.close()


def test_on_failed_auth_no_future_does_not_raise():
    adapter = make_adapter()
    adapter._connect_future = None
    adapter._on_failed_auth({})  # should not raise


def test_on_failed_auth_already_done_future_does_not_raise():
    adapter = make_adapter()
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        future.set_result(True)
        adapter._connect_future = future
        adapter._on_failed_auth({})  # should not raise InvalidStateError
    finally:
        loop.close()

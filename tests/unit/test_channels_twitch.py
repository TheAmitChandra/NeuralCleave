"""Unit tests for neuralcleave.channels.twitch — TwitchAdapter.

Covers:
  - Constructor / defaults / config parsing (token strip, channel normalization)
  - is_connected lifecycle
  - connect() / disconnect()
  - _parse_irc_line() — tags, prefix, command, params, trailing; edge cases
  - _handle_irc_line() — PING/PONG, PRIVMSG dispatch, auth NOTICE, RECONNECT
  - _process_privmsg() — tags extraction, bot echo skip, empty text, timestamp
  - _authenticate() — CAP REQ / PASS / NICK / JOIN sequence
  - send() — connected, not connected, with/without # prefix, empty target
  - ping() — 200 valid, 401 invalid, network error, no token
  - get_config_schema() — shape and required fields
  - Constants
  - Edge / integration cases
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.twitch import (
    _CAP_REQ,
    _IRC_HOST,
    _IRC_PORT,
    _VALIDATE_URL,
    TwitchAdapter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_adapter(**overrides: Any) -> TwitchAdapter:
    cfg: dict[str, Any] = {
        "token": "mytoken123",
        "bot_username": "NeuralCleaveBot",
        "channels": ["mychannel", "otherchannel"],
        **overrides,
    }
    return TwitchAdapter(cfg)


def fake_ws() -> MagicMock:
    ws = AsyncMock()
    ws.send_str = AsyncMock()
    ws.close = AsyncMock()
    ws.closed = False
    return ws


def fake_response(status: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=json_data or {})
    return resp


def fake_http_client(response: MagicMock) -> MagicMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _privmsg_line(
    nick: str = "alice",
    channel: str = "#mychannel",
    text: str = "Hello!",
    user_id: str = "12345",
    display_name: str = "Alice",
    ts_ms: str = "1700000000000",
    msg_id: str = "abc-123",
) -> str:
    tags = (
        f"@badge-info=;badges=;color=#FF0000;display-name={display_name};"
        f"emotes=;first-msg=0;id={msg_id};mod=0;room-id=99999;"
        f"subscriber=0;tmi-sent-ts={ts_ms};turbo=0;user-id={user_id};user-type="
    )
    return f"{tags} :{nick}!{nick}@{nick}.tmi.twitch.tv PRIVMSG {channel} :{text}"


# ===========================================================================
# 1. Constructor / defaults
# ===========================================================================


class TestConstructor:
    def test_default_token_empty(self):
        assert TwitchAdapter({})._token == ""

    def test_default_bot_username_empty(self):
        assert TwitchAdapter({})._bot_username == ""

    def test_default_channels_empty(self):
        assert TwitchAdapter({})._channels == []

    def test_default_host(self):
        assert make_adapter()._host == _IRC_HOST

    def test_default_port(self):
        assert make_adapter()._port == _IRC_PORT

    def test_default_reconnect_delay(self):
        assert make_adapter()._reconnect_delay == 5.0

    def test_ws_task_none_initially(self):
        assert make_adapter()._ws_task is None

    def test_irc_ws_none_initially(self):
        assert make_adapter()._irc_ws is None

    def test_token_oauth_prefix_stripped(self):
        a = TwitchAdapter({"token": "oauth:mytoken"})
        assert a._token == "mytoken"

    def test_token_without_prefix_unchanged(self):
        a = TwitchAdapter({"token": "mytoken"})
        assert a._token == "mytoken"

    def test_bot_username_lowercased(self):
        a = TwitchAdapter({"bot_username": "MyBot"})
        assert a._bot_username == "mybot"

    def test_channels_stripped_of_hash(self):
        a = TwitchAdapter({"channels": ["#chan1", "chan2", "#chan3"]})
        assert a._channels == ["chan1", "chan2", "chan3"]

    def test_channels_lowercased(self):
        a = TwitchAdapter({"channels": ["ChanA", "CHANB"]})
        assert a._channels == ["chana", "chanb"]

    def test_string_channels_coerced_to_list(self):
        a = TwitchAdapter({"channels": "mychannel"})
        assert a._channels == ["mychannel"]

    def test_custom_host(self):
        assert make_adapter(host="irc.example.com")._host == "irc.example.com"

    def test_custom_port_int(self):
        assert make_adapter(port=6697)._port == 6697

    def test_custom_port_string_coerced(self):
        assert make_adapter(port="6697")._port == 6697

    def test_custom_reconnect_delay(self):
        assert make_adapter(reconnect_delay=10.0)._reconnect_delay == 10.0

    def test_reconnect_delay_coerced_to_float(self):
        assert isinstance(make_adapter(reconnect_delay=3)._reconnect_delay, float)

    def test_channel_id(self):
        assert TwitchAdapter.channel_id == "twitch"

    def test_channel_id_on_instance(self):
        assert make_adapter().channel_id == "twitch"


# ===========================================================================
# 2. is_connected
# ===========================================================================


class TestIsConnected:
    def test_not_connected_initially(self):
        assert not make_adapter().is_connected

    def test_connected_when_ws_task_set(self):
        a = make_adapter()
        a._ws_task = MagicMock()
        assert a.is_connected

    def test_not_connected_after_task_cleared(self):
        a = make_adapter()
        a._ws_task = MagicMock()
        a._ws_task = None
        assert not a.is_connected


# ===========================================================================
# 3. connect() / disconnect()
# ===========================================================================


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_connect_sets_ws_task(self):
        a = make_adapter()
        with patch.object(a, "_irc_loop", new=AsyncMock()):
            await a.connect()
        assert a._ws_task is not None
        a._ws_task.cancel()

    @pytest.mark.asyncio
    async def test_connect_sets_stop_event(self):
        a = make_adapter()
        with patch.object(a, "_irc_loop", new=AsyncMock()):
            await a.connect()
        assert a._stop_event is not None
        a._ws_task.cancel()

    @pytest.mark.asyncio
    async def test_disconnect_sets_stop_event(self):
        a = make_adapter()
        stop = asyncio.Event()
        a._stop_event = stop
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        a._ws_task = mock_task
        await a.disconnect()
        assert stop.is_set()

    @pytest.mark.asyncio
    async def test_disconnect_clears_ws_task(self):
        a = make_adapter()
        a._stop_event = asyncio.Event()
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        a._ws_task = mock_task
        await a.disconnect()
        assert a._ws_task is None

    @pytest.mark.asyncio
    async def test_disconnect_clears_irc_ws(self):
        a = make_adapter()
        a._stop_event = asyncio.Event()
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        a._ws_task = mock_task
        a._irc_ws = AsyncMock()
        await a.disconnect()
        assert a._irc_ws is None

    @pytest.mark.asyncio
    async def test_disconnect_closes_irc_ws(self):
        a = make_adapter()
        a._stop_event = asyncio.Event()
        mock_ws = AsyncMock()
        a._irc_ws = mock_ws
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        a._ws_task = mock_task
        await a.disconnect()
        mock_ws.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_safe_when_not_connected(self):
        a = make_adapter()
        await a.disconnect()
        assert a._ws_task is None

    @pytest.mark.asyncio
    async def test_double_disconnect_safe(self):
        a = make_adapter()
        a._stop_event = asyncio.Event()
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        a._ws_task = mock_task
        await a.disconnect()
        await a.disconnect()
        assert a._ws_task is None


# ===========================================================================
# 4. _parse_irc_line()
# ===========================================================================


class TestParseIrcLine:
    def _parse(self, line: str):
        return TwitchAdapter._parse_irc_line(line)

    def test_empty_line(self):
        tags, prefix, cmd, params, trailing = self._parse("")
        assert cmd == ""
        assert tags == {}
        assert params == []

    def test_simple_ping(self):
        tags, prefix, cmd, params, trailing = self._parse("PING :tmi.twitch.tv")
        assert cmd == "PING"
        assert trailing == "tmi.twitch.tv"

    def test_simple_pong(self):
        tags, prefix, cmd, params, trailing = self._parse("PONG :tmi.twitch.tv")
        assert cmd == "PONG"

    def test_001_welcome(self):
        _, _, cmd, params, trailing = self._parse(
            ":tmi.twitch.tv 001 neuralcleavebot :Welcome, GLHF!"
        )
        assert cmd == "001"
        assert trailing == "Welcome, GLHF!"

    def test_privmsg_with_tags(self):
        line = _privmsg_line(nick="alice", text="Hello!")
        tags, prefix, cmd, params, trailing = self._parse(line)
        assert cmd == "PRIVMSG"
        assert trailing == "Hello!"
        assert params == ["#mychannel"]

    def test_tags_extracted(self):
        line = _privmsg_line(user_id="99999", display_name="TestUser", ts_ms="1700000001000")
        tags, _, _, _, _ = self._parse(line)
        assert tags["user-id"] == "99999"
        assert tags["display-name"] == "TestUser"
        assert tags["tmi-sent-ts"] == "1700000001000"

    def test_prefix_extracted(self):
        line = _privmsg_line(nick="alice")
        _, prefix, _, _, _ = self._parse(line)
        assert prefix.startswith("alice!")

    def test_channel_in_params(self):
        line = _privmsg_line(channel="#testchan", text="hi")
        _, _, _, params, _ = self._parse(line)
        assert "#testchan" in params

    def test_trailing_text(self):
        line = _privmsg_line(text="Hello there!")
        _, _, _, _, trailing = self._parse(line)
        assert trailing == "Hello there!"

    def test_text_with_colon_in_middle(self):
        line = _privmsg_line(text="time: 12:30")
        _, _, _, _, trailing = self._parse(line)
        assert trailing == "time: 12:30"

    def test_no_tags(self):
        line = ":alice!alice@alice.tmi.twitch.tv PRIVMSG #chan :hello"
        tags, prefix, cmd, params, trailing = self._parse(line)
        assert tags == {}
        assert cmd == "PRIVMSG"
        assert trailing == "hello"

    def test_tag_without_value(self):
        line = "@mod :alice!alice@alice.tmi.twitch.tv PRIVMSG #chan :hi"
        tags, _, _, _, _ = self._parse(line)
        assert "mod" in tags

    def test_notice_command(self):
        line = ":tmi.twitch.tv NOTICE * :Login authentication failed"
        _, _, cmd, _, trailing = self._parse(line)
        assert cmd == "NOTICE"
        assert "Login authentication failed" in trailing

    def test_reconnect_command(self):
        _, _, cmd, _, _ = self._parse(":tmi.twitch.tv RECONNECT")
        assert cmd == "RECONNECT"

    def test_command_uppercased(self):
        _, _, cmd, _, _ = self._parse("ping :tmi.twitch.tv")
        assert cmd == "PING"

    def test_no_trailing(self):
        _, _, cmd, params, trailing = self._parse(
            ":tmi.twitch.tv JOIN #mychannel"
        )
        assert cmd == "JOIN"
        assert trailing == ""
        assert "#mychannel" in params

    def test_cap_ack(self):
        _, _, cmd, params, trailing = self._parse(
            ":tmi.twitch.tv CAP * ACK :twitch.tv/tags twitch.tv/commands"
        )
        assert cmd == "CAP"
        assert "twitch.tv/tags" in trailing


# ===========================================================================
# 5. _handle_irc_line()
# ===========================================================================


class TestHandleIrcLine:
    @pytest.mark.asyncio
    async def test_ping_sends_pong(self):
        a = make_adapter()
        ws = fake_ws()
        await a._handle_irc_line("PING :tmi.twitch.tv", ws)
        ws.send_str.assert_awaited_once_with("PONG :tmi.twitch.tv\r\n")

    @pytest.mark.asyncio
    async def test_privmsg_calls_process(self):
        a = make_adapter()
        ws = fake_ws()
        with patch.object(a, "_process_privmsg", new=AsyncMock()) as mock_proc:
            await a._handle_irc_line(_privmsg_line(), ws)
        mock_proc.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notice_auth_failed_logged(self):
        a = make_adapter()
        ws = fake_ws()
        line = ":tmi.twitch.tv NOTICE * :Login authentication failed"
        await a._handle_irc_line(line, ws)
        ws.send_str.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_notice_improperly_formatted_auth(self):
        a = make_adapter()
        ws = fake_ws()
        line = ":tmi.twitch.tv NOTICE * :Improperly formatted auth"
        await a._handle_irc_line(line, ws)
        ws.send_str.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconnect_closes_ws(self):
        a = make_adapter()
        ws = fake_ws()
        await a._handle_irc_line(":tmi.twitch.tv RECONNECT", ws)
        ws.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unrecognised_command_no_crash(self):
        a = make_adapter()
        ws = fake_ws()
        await a._handle_irc_line(":tmi.twitch.tv 375 neuralcleavebot :motd", ws)

    @pytest.mark.asyncio
    async def test_empty_line_no_crash(self):
        a = make_adapter()
        ws = fake_ws()
        await a._handle_irc_line("", ws)


# ===========================================================================
# 6. _process_privmsg()
# ===========================================================================


class TestProcessPrivmsg:
    def _tags_from_line(self, line: str) -> dict[str, str]:
        tags, _, _, _, _ = TwitchAdapter._parse_irc_line(line)
        return tags

    def _prefix_params_trailing(self, line: str):
        tags, prefix, _, params, trailing = TwitchAdapter._parse_irc_line(line)
        return tags, prefix, params, trailing

    @pytest.mark.asyncio
    async def test_dispatches_message(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        tags, prefix, params, trailing = self._prefix_params_trailing(
            _privmsg_line(text="Hello!")
        )
        await a._process_privmsg(tags, prefix, params, trailing)
        await asyncio.sleep(0)
        assert len(msgs) == 1
        assert msgs[0].text == "Hello!"

    @pytest.mark.asyncio
    async def test_channel_in_thread_id(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        tags, prefix, params, trailing = self._prefix_params_trailing(
            _privmsg_line(channel="#mystreamer")
        )
        await a._process_privmsg(tags, prefix, params, trailing)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "mystreamer"

    @pytest.mark.asyncio
    async def test_display_name_used_as_sender_name(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        tags, prefix, params, trailing = self._prefix_params_trailing(
            _privmsg_line(nick="alice", display_name="Alice_Wonderland")
        )
        await a._process_privmsg(tags, prefix, params, trailing)
        await asyncio.sleep(0)
        assert msgs[0].sender_name == "Alice_Wonderland"

    @pytest.mark.asyncio
    async def test_user_id_tag_as_sender_id(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        tags, prefix, params, trailing = self._prefix_params_trailing(
            _privmsg_line(user_id="999888")
        )
        await a._process_privmsg(tags, prefix, params, trailing)
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "999888"

    @pytest.mark.asyncio
    async def test_timestamp_from_tmi_sent_ts(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        tags, prefix, params, trailing = self._prefix_params_trailing(
            _privmsg_line(ts_ms="1700000000000")
        )
        await a._process_privmsg(tags, prefix, params, trailing)
        await asyncio.sleep(0)
        assert msgs[0].timestamp == 1700000000.0

    @pytest.mark.asyncio
    async def test_missing_ts_falls_back_to_now(self):
        import time
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        before = time.time()
        await a._process_privmsg({}, "alice!alice@alice.tmi.twitch.tv", ["#chan"], "hi")
        await asyncio.sleep(0)
        after = time.time()
        assert before - 0.1 <= msgs[0].timestamp <= after + 1

    @pytest.mark.asyncio
    async def test_bot_echo_skipped(self):
        a = make_adapter(bot_username="neuralcleavebot")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        tags, prefix, params, trailing = self._prefix_params_trailing(
            _privmsg_line(nick="neuralcleavebot", display_name="NeuralCleaveBot")
        )
        await a._process_privmsg(tags, prefix, params, trailing)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_bot_echo_case_insensitive(self):
        a = make_adapter(bot_username="neuralcleavebot")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        await a._process_privmsg({}, "NeuralCleaveBot!neuralcleavebot@neuralcleavebot.tmi.twitch.tv", ["#chan"], "hi")
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_empty_text_not_dispatched(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        await a._process_privmsg({}, "alice!alice@alice.tmi.twitch.tv", ["#chan"], "")
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_whitespace_only_text_not_dispatched(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        await a._process_privmsg({}, "alice!alice@alice.tmi.twitch.tv", ["#chan"], "   ")
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_message_channel_id(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        await a._process_privmsg({}, "alice!alice@alice.tmi.twitch.tv", ["#chan"], "hi")
        await asyncio.sleep(0)
        assert msgs[0].channel == "twitch"

    @pytest.mark.asyncio
    async def test_raw_contains_tags(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        tags = {"user-id": "123", "display-name": "Alice"}
        await a._process_privmsg(tags, "alice!alice@alice.tmi.twitch.tv", ["#chan"], "hi")
        await asyncio.sleep(0)
        assert msgs[0].raw["tags"] == tags

    @pytest.mark.asyncio
    async def test_msg_id_in_raw(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        tags, prefix, params, trailing = self._prefix_params_trailing(
            _privmsg_line(msg_id="unique-uuid-123")
        )
        await a._process_privmsg(tags, prefix, params, trailing)
        await asyncio.sleep(0)
        assert msgs[0].raw["id"] == "unique-uuid-123"

    @pytest.mark.asyncio
    async def test_no_handler_no_crash(self):
        a = make_adapter()
        await a._process_privmsg({}, "alice!alice@alice.tmi.twitch.tv", ["#chan"], "hi")
        await asyncio.sleep(0)


# ===========================================================================
# 7. _authenticate()
# ===========================================================================


class TestAuthenticate:
    @pytest.mark.asyncio
    async def test_sends_cap_req(self):
        a = make_adapter()
        ws = fake_ws()
        await a._authenticate(ws)
        calls = [c[0][0] for c in ws.send_str.call_args_list]
        assert _CAP_REQ in calls

    @pytest.mark.asyncio
    async def test_sends_pass_with_oauth_prefix(self):
        a = make_adapter(token="mytoken")
        ws = fake_ws()
        await a._authenticate(ws)
        calls = [c[0][0] for c in ws.send_str.call_args_list]
        assert "PASS oauth:mytoken\r\n" in calls

    @pytest.mark.asyncio
    async def test_sends_nick(self):
        a = make_adapter(bot_username="MyBot")
        ws = fake_ws()
        await a._authenticate(ws)
        calls = [c[0][0] for c in ws.send_str.call_args_list]
        assert "NICK mybot\r\n" in calls

    @pytest.mark.asyncio
    async def test_joins_all_channels(self):
        a = make_adapter(channels=["chan1", "#chan2"])
        ws = fake_ws()
        await a._authenticate(ws)
        calls = [c[0][0] for c in ws.send_str.call_args_list]
        assert "JOIN #chan1\r\n" in calls
        assert "JOIN #chan2\r\n" in calls

    @pytest.mark.asyncio
    async def test_no_channels_no_join(self):
        a = make_adapter(channels=[])
        ws = fake_ws()
        await a._authenticate(ws)
        calls = [c[0][0] for c in ws.send_str.call_args_list]
        assert not any("JOIN" in c for c in calls)

    @pytest.mark.asyncio
    async def test_cap_req_sent_before_pass(self):
        a = make_adapter()
        ws = fake_ws()
        await a._authenticate(ws)
        calls = [c[0][0] for c in ws.send_str.call_args_list]
        cap_idx = calls.index(_CAP_REQ)
        pass_idx = next(i for i, c in enumerate(calls) if c.startswith("PASS"))
        assert cap_idx < pass_idx


# ===========================================================================
# 8. send()
# ===========================================================================


class TestSend:
    @pytest.mark.asyncio
    async def test_empty_target_returns_none(self):
        assert await make_adapter().send("", "hi") is None

    @pytest.mark.asyncio
    async def test_not_connected_returns_none(self):
        a = make_adapter()
        a._irc_ws = None
        assert await a.send("mychannel", "hi") is None

    @pytest.mark.asyncio
    async def test_sends_privmsg(self):
        a = make_adapter()
        ws = fake_ws()
        a._irc_ws = ws
        await a.send("mychannel", "Hello!")
        ws.send_str.assert_awaited_once_with("PRIVMSG #mychannel :Hello!\r\n")

    @pytest.mark.asyncio
    async def test_target_with_hash_normalized(self):
        a = make_adapter()
        ws = fake_ws()
        a._irc_ws = ws
        await a.send("#mychannel", "hi")
        ws.send_str.assert_awaited_once_with("PRIVMSG #mychannel :hi\r\n")

    @pytest.mark.asyncio
    async def test_target_uppercased_lowercased(self):
        a = make_adapter()
        ws = fake_ws()
        a._irc_ws = ws
        await a.send("MyChannel", "hi")
        ws.send_str.assert_awaited_once_with("PRIVMSG #mychannel :hi\r\n")

    @pytest.mark.asyncio
    async def test_success_returns_channel_with_hash(self):
        a = make_adapter()
        ws = fake_ws()
        a._irc_ws = ws
        result = await a.send("mychannel", "hi")
        assert result == "#mychannel"

    @pytest.mark.asyncio
    async def test_send_error_returns_none(self):
        a = make_adapter()
        ws = fake_ws()
        ws.send_str = AsyncMock(side_effect=ConnectionError("closed"))
        a._irc_ws = ws
        result = await a.send("mychannel", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_unicode_message_sent(self):
        a = make_adapter()
        ws = fake_ws()
        a._irc_ws = ws
        await a.send("chan", "こんにちは 🌸")
        call_arg = ws.send_str.call_args[0][0]
        assert "こんにちは 🌸" in call_arg


# ===========================================================================
# 9. ping()
# ===========================================================================


class TestPing:
    @pytest.mark.asyncio
    async def test_no_token_returns_false(self):
        assert await make_adapter(token="").ping() is False

    @pytest.mark.asyncio
    async def test_200_returns_true(self):
        a = make_adapter()
        resp = fake_response(200, {"client_id": "abc", "login": "neuralcleavebot"})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            assert await a.ping() is True

    @pytest.mark.asyncio
    async def test_401_returns_false(self):
        a = make_adapter()
        resp = fake_response(401, {"status": 401, "message": "invalid access token"})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        a = make_adapter()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=client):
            assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_uses_validate_url(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        url = client.get.call_args[0][0]
        assert url == _VALIDATE_URL

    @pytest.mark.asyncio
    async def test_sends_oauth_header(self):
        a = make_adapter(token="mytoken123")
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        headers = client.get.call_args[1]["headers"]
        assert headers["Authorization"] == "OAuth mytoken123"

    @pytest.mark.asyncio
    async def test_timeout_5s(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        assert client.get.call_args[1]["timeout"] == 5.0


# ===========================================================================
# 10. get_config_schema()
# ===========================================================================


class TestConfigSchema:
    def test_returns_dict(self):
        assert isinstance(make_adapter().get_config_schema(), dict)

    def test_type_is_object(self):
        assert make_adapter().get_config_schema()["type"] == "object"

    def test_required_has_token(self):
        assert "token" in make_adapter().get_config_schema()["required"]

    def test_required_has_bot_username(self):
        assert "bot_username" in make_adapter().get_config_schema()["required"]

    def test_properties_has_all_keys(self):
        props = make_adapter().get_config_schema()["properties"]
        for key in ("token", "bot_username", "channels", "host", "port", "reconnect_delay"):
            assert key in props, f"Missing property: {key}"

    def test_host_default(self):
        props = make_adapter().get_config_schema()["properties"]
        assert props["host"]["default"] == "irc-ws.chat.twitch.tv"

    def test_port_default(self):
        props = make_adapter().get_config_schema()["properties"]
        assert props["port"]["default"] == 443

    def test_reconnect_delay_default(self):
        props = make_adapter().get_config_schema()["properties"]
        assert props["reconnect_delay"]["default"] == 5.0

    def test_channels_default_is_empty_list(self):
        props = make_adapter().get_config_schema()["properties"]
        assert props["channels"]["default"] == []


# ===========================================================================
# 11. Constants
# ===========================================================================


class TestConstants:
    def test_irc_host(self):
        assert _IRC_HOST == "irc-ws.chat.twitch.tv"

    def test_irc_port(self):
        assert _IRC_PORT == 443

    def test_validate_url(self):
        assert _VALIDATE_URL == "https://id.twitch.tv/oauth2/validate"

    def test_cap_req_has_tags(self):
        assert "twitch.tv/tags" in _CAP_REQ

    def test_cap_req_has_commands(self):
        assert "twitch.tv/commands" in _CAP_REQ

    def test_cap_req_ends_with_crlf(self):
        assert _CAP_REQ.endswith("\r\n")


# ===========================================================================
# 12. Edge / integration cases
# ===========================================================================


class TestEdgeCases:
    def test_repr_contains_channel_id(self):
        assert "twitch" in repr(make_adapter())

    @pytest.mark.asyncio
    async def test_multiple_lines_in_one_ws_frame(self):
        """Multiple IRC lines in one WebSocket frame are all handled."""
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        ws = fake_ws()
        lines = [
            _privmsg_line(nick="alice", text="First message"),
            _privmsg_line(nick="bob", text="Second message"),
        ]
        combined = "\r\n".join(lines)
        for line in combined.split("\r\n"):
            line = line.strip()
            if line:
                await a._handle_irc_line(line, ws)
        await asyncio.sleep(0)
        assert len(msgs) == 2
        assert msgs[0].text == "First message"
        assert msgs[1].text == "Second message"

    @pytest.mark.asyncio
    async def test_ping_pong_does_not_dispatch_message(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        ws = fake_ws()
        await a._handle_irc_line("PING :tmi.twitch.tv", ws)
        await asyncio.sleep(0)
        assert msgs == []
        ws.send_str.assert_awaited_once_with("PONG :tmi.twitch.tv\r\n")

    @pytest.mark.asyncio
    async def test_send_while_disconnected_returns_none(self):
        a = make_adapter()
        assert a._irc_ws is None
        result = await a.send("mychannel", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_unicode_channel_name(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        tags, prefix, cmd, params, trailing = TwitchAdapter._parse_irc_line(
            ":alice!alice@alice.tmi.twitch.tv PRIVMSG #streamerchan :こんにちは"
        )
        await a._process_privmsg(tags, prefix, params, trailing)
        await asyncio.sleep(0)
        assert msgs[0].text == "こんにちは"

    @pytest.mark.asyncio
    async def test_token_stripped_of_oauth_prefix_used_in_auth(self):
        a = TwitchAdapter({"token": "oauth:abc123", "bot_username": "bot", "channels": []})
        ws = fake_ws()
        await a._authenticate(ws)
        calls = [c[0][0] for c in ws.send_str.call_args_list]
        assert "PASS oauth:abc123\r\n" in calls
        assert not any("oauth:oauth:" in c for c in calls)

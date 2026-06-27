"""Unit tests for cortexflow.channels.irc — IRCAdapter and helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from cortexflow_ai.channels.irc import IRCAdapter, _split_message

# ---------------------------------------------------------------------------
# _split_message helper
# ---------------------------------------------------------------------------


def test_split_message_short_no_split():
    parts = _split_message("hello", max_len=400)
    assert parts == ["hello"]


def test_split_message_exact_length_no_split():
    text = "x" * 400
    parts = _split_message(text, max_len=400)
    assert len(parts) == 1
    assert parts[0] == text


def test_split_message_over_limit():
    text = "x" * 850
    parts = _split_message(text, max_len=400)
    assert len(parts) == 3
    assert "".join(parts) == text
    assert all(len(p) <= 400 for p in parts)


def test_split_message_empty():
    parts = _split_message("", max_len=400)
    assert parts == [""]


# ---------------------------------------------------------------------------
# IRCAdapter metadata
# ---------------------------------------------------------------------------


def test_channel_id():
    assert IRCAdapter({}).channel_id == "irc"


def test_default_server():
    a = IRCAdapter({})
    assert a._server == "irc.libera.chat"


def test_default_port():
    a = IRCAdapter({})
    assert a._port == 6697


def test_default_tls():
    a = IRCAdapter({})
    assert a._tls is True


def test_custom_nick():
    a = IRCAdapter({"nick": "mybot"})
    assert a._nick == "mybot"


def test_channels_parsed():
    a = IRCAdapter({"channels": ["#one", "#two"]})
    assert "#one" in a._channels
    assert "#two" in a._channels


def test_config_schema_has_server():
    schema = IRCAdapter({}).get_config_schema()
    assert "server" in schema["properties"]


# ---------------------------------------------------------------------------
# send() when not connected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_returns_none_when_not_connected():
    a = IRCAdapter({"server": "irc.example.com", "nick": "bot"})
    result = await a.send("#channel", "hello")
    assert result is None


# ---------------------------------------------------------------------------
# ENV: resolution
# ---------------------------------------------------------------------------


def test_resolve_sasl_env(monkeypatch):
    monkeypatch.setenv("IRC_SASL_PASS", "s3cr3t")
    a = IRCAdapter({"sasl_password": "ENV:IRC_SASL_PASS"})
    assert a._sasl_password == "s3cr3t"


# ---------------------------------------------------------------------------
# _process_line — PING/PONG
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_line_ping_sends_pong():
    a = IRCAdapter({"nick": "bot"})
    sent = []

    async def _fake_send(line):
        sent.append(line)

    a._send_raw = _fake_send
    await a._process_line("PING :irc.example.com")
    assert any("PONG" in s for s in sent)


# ---------------------------------------------------------------------------
# _process_line — PRIVMSG dispatches handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_line_privmsg_dispatches_handler():
    import asyncio

    a = IRCAdapter({"nick": "bot"})
    received = []

    async def _handler(msg):
        received.append(msg)

    a.on_message(_handler)
    a._send_raw = lambda _: None  # noop

    await a._process_line(":alice!alice@host.com PRIVMSG #channel :Hello IRC!")
    await asyncio.sleep(0)

    assert len(received) == 1
    assert received[0].sender_id == "alice"
    assert received[0].text == "Hello IRC!"
    assert received[0].thread_id == "#channel"


@pytest.mark.asyncio
async def test_process_line_privmsg_pm_thread_id_none():
    import asyncio

    a = IRCAdapter({"nick": "bot"})
    received = []

    async def _handler(msg):
        received.append(msg)

    a.on_message(_handler)
    a._send_raw = lambda _: None

    await a._process_line(":alice!alice@host.com PRIVMSG bot :PM message")
    await asyncio.sleep(0)

    assert len(received) == 1
    assert received[0].thread_id is None  # PM has no channel thread


@pytest.mark.asyncio
async def test_process_line_001_joins_channels():
    a = IRCAdapter({"nick": "bot", "channels": ["#test"]})
    sent = []

    async def _fake_send(line):
        sent.append(line)

    a._send_raw = _fake_send
    await a._process_line(":irc.example.com 001 bot :Welcome")
    assert any("JOIN #test" in s for s in sent)


# ---------------------------------------------------------------------------
# _process_line — CAP ACK / AUTHENTICATE (SASL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_line_cap_ack_sends_authenticate_plain():
    a = IRCAdapter({"nick": "bot"})
    sent = []

    async def _fake_send(line):
        sent.append(line)

    a._send_raw = _fake_send

    await a._process_line(":irc.example.com CAP * ACK :sasl")

    assert any("AUTHENTICATE PLAIN" in s for s in sent)


@pytest.mark.asyncio
async def test_process_line_authenticate_challenge_sends_credentials():
    a = IRCAdapter({"nick": "bot", "sasl_user": "myuser", "sasl_password": "mypass"})
    sent = []

    async def _fake_send(line):
        sent.append(line)

    a._send_raw = _fake_send

    await a._process_line("AUTHENTICATE +")

    assert any(s.startswith("AUTHENTICATE ") and "AUTHENTICATE +" not in s for s in sent)
    assert any("CAP END" in s for s in sent)


# ---------------------------------------------------------------------------
# _process_line — CTCP ACTION stripping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_line_ctcp_action_stripped():
    a = IRCAdapter({"nick": "bot"})
    received = []

    async def _handler(msg):
        received.append(msg)

    a.on_message(_handler)
    a._send_raw = lambda _: None

    await a._process_line(":alice!alice@host.com PRIVMSG #channel :\x01ACTION waves\x01")
    await asyncio.sleep(0)

    assert received[0].text == "* waves"


@pytest.mark.asyncio
async def test_process_line_empty_line_returns():
    a = IRCAdapter({"nick": "bot"})
    await a._process_line("")  # should not raise


@pytest.mark.asyncio
async def test_process_line_too_few_parts_returns():
    a = IRCAdapter({"nick": "bot"})
    await a._process_line("ONLYONEWORD")  # should not raise


# ---------------------------------------------------------------------------
# _send_raw
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_raw_no_writer_is_noop():
    a = IRCAdapter({"nick": "bot"})
    await a._send_raw("NICK bot")  # no writer set — should not raise


@pytest.mark.asyncio
async def test_send_raw_writes_and_drains():
    a = IRCAdapter({"nick": "bot"})
    a._writer = MagicMock()
    a._writer.write = MagicMock()
    a._writer.drain = AsyncMock()

    await a._send_raw("PRIVMSG #chan :hi")

    a._writer.write.assert_called_once()
    a._writer.drain.assert_awaited_once()


# ---------------------------------------------------------------------------
# send() — connected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_writes_privmsg_when_connected():
    a = IRCAdapter({"nick": "bot"})
    a._connected = True
    a._writer = MagicMock()
    a._writer.write = MagicMock()
    a._writer.drain = AsyncMock()

    result = await a.send("#channel", "hello there")

    assert result is None
    a._writer.write.assert_called_once()
    sent_bytes = a._writer.write.call_args[0][0]
    assert b"PRIVMSG #channel :hello there" in sent_bytes


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_opens_connection_and_authenticates(monkeypatch):
    a = IRCAdapter({"server": "irc.example.com", "nick": "bot"})
    mock_reader = MagicMock()
    mock_writer = MagicMock()
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock()

    monkeypatch.setattr(asyncio, "open_connection", AsyncMock(return_value=(mock_reader, mock_writer)))
    monkeypatch.setattr(a, "_read_loop", AsyncMock())

    await a.connect()

    assert a._connected is True
    assert a._reader is mock_reader
    assert a._writer is mock_writer
    assert a._read_task is not None
    # NICK and USER should have been sent
    assert mock_writer.write.call_count >= 2

    await a.disconnect()


@pytest.mark.asyncio
async def test_connect_with_sasl_sends_cap_req(monkeypatch):
    a = IRCAdapter({"server": "irc.example.com", "nick": "bot", "sasl_user": "u", "sasl_password": "p"})
    mock_reader = MagicMock()
    mock_writer = MagicMock()
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock()

    monkeypatch.setattr(asyncio, "open_connection", AsyncMock(return_value=(mock_reader, mock_writer)))
    monkeypatch.setattr(a, "_read_loop", AsyncMock())

    await a.connect()

    sent_lines = [call.args[0] for call in mock_writer.write.call_args_list]
    assert any(b"CAP REQ" in line for line in sent_lines)

    await a.disconnect()


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_with_no_writer_or_task_is_noop():
    a = IRCAdapter({"nick": "bot"})
    await a.disconnect()  # should not raise


@pytest.mark.asyncio
async def test_disconnect_sends_quit_and_closes_writer():
    a = IRCAdapter({"nick": "bot"})
    a._connected = True
    mock_writer = MagicMock()
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    a._writer = mock_writer
    a._reader = MagicMock()

    await a.disconnect()

    assert a._connected is False
    assert a._writer is None
    assert a._reader is None
    mock_writer.close.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_swallows_writer_close_exception():
    a = IRCAdapter({"nick": "bot"})
    mock_writer = MagicMock()
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock(side_effect=Exception("connection reset"))
    a._writer = mock_writer

    await a.disconnect()  # should not raise

    assert a._writer is None


@pytest.mark.asyncio
async def test_disconnect_cancels_read_task():
    a = IRCAdapter({"nick": "bot"})

    async def _never_ending():
        await asyncio.sleep(100)

    a._read_task = asyncio.create_task(_never_ending())

    await a.disconnect()

    assert a._read_task is None


# ---------------------------------------------------------------------------
# _read_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_loop_no_reader_returns_immediately():
    a = IRCAdapter({"nick": "bot"})
    await a._read_loop()  # no reader set


@pytest.mark.asyncio
async def test_read_loop_processes_lines_until_eof():
    a = IRCAdapter({"nick": "bot"})
    a._connected = True
    processed = []
    a._process_line = lambda line: processed.append(line) or asyncio.sleep(0)

    lines = [b"PING :server\r\n", b""]  # second readline() call returns EOF
    mock_reader = MagicMock()
    mock_reader.readline = AsyncMock(side_effect=lines)
    a._reader = mock_reader

    await a._read_loop()

    assert processed == ["PING :server"]


@pytest.mark.asyncio
async def test_read_loop_swallows_cancelled_error():
    a = IRCAdapter({"nick": "bot"})
    a._connected = True
    mock_reader = MagicMock()
    mock_reader.readline = AsyncMock(side_effect=asyncio.CancelledError())
    a._reader = mock_reader

    await a._read_loop()  # should not raise


@pytest.mark.asyncio
async def test_read_loop_logs_generic_exception():
    a = IRCAdapter({"nick": "bot"})
    a._connected = True
    mock_reader = MagicMock()
    mock_reader.readline = AsyncMock(side_effect=RuntimeError("socket error"))
    a._reader = mock_reader

    await a._read_loop()  # should not raise, just logged

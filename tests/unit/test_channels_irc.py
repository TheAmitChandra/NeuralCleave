"""Unit tests for cortexflow.channels.irc — IRCAdapter and helpers."""

from __future__ import annotations

import pytest

from cortexflow.channels.irc import IRCAdapter, _split_message


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

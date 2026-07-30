"""Tests for /voice listen on|off|status in CommandHandler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from neuralcleave.commands.handler import CommandHandler


class FakeSession:
    def __init__(self) -> None:
        self.voice_mode = False
        self.session_id = "test-session"
        self.channel = "test"
        self.turn_count = 0
        self.idle_seconds = 0.0

    def clear(self) -> None:
        self.turn_count = 0


def _make_handler() -> CommandHandler:
    return CommandHandler.make_default()


def _make_cont(*, is_listening: bool = False) -> MagicMock:
    cont = MagicMock()
    cont.is_listening = is_listening
    cont.start = AsyncMock()
    cont.stop = AsyncMock()
    return cont


def _make_runtime(*, cont=None) -> MagicMock:
    rt = MagicMock()
    rt._continuous = cont
    return rt


# ---------------------------------------------------------------------------
# /voice on|off (existing — must still work)
# ---------------------------------------------------------------------------


class TestVoiceOnOff:
    @pytest.mark.asyncio
    async def test_voice_on_enables_mode(self) -> None:
        h = _make_handler()
        session = FakeSession()
        result = await h.dispatch("/voice on", session=session)
        assert result.handled
        assert "enabled" in result.text.lower()
        assert session.voice_mode is True

    @pytest.mark.asyncio
    async def test_voice_off_disables_mode(self) -> None:
        h = _make_handler()
        session = FakeSession()
        session.voice_mode = True
        result = await h.dispatch("/voice off", session=session)
        assert result.handled
        assert "disabled" in result.text.lower()
        assert session.voice_mode is False

    @pytest.mark.asyncio
    async def test_voice_no_session_returns_error(self) -> None:
        h = _make_handler()
        result = await h.dispatch("/voice on")
        assert result.handled
        assert "session" in result.text.lower()


# ---------------------------------------------------------------------------
# /voice listen — no continuous configured
# ---------------------------------------------------------------------------


class TestVoiceListenNoContinuous:
    @pytest.mark.asyncio
    async def test_no_runtime_returns_not_configured(self) -> None:
        h = _make_handler()
        result = await h.dispatch("/voice listen on", session=FakeSession())
        assert result.handled
        assert "not configured" in result.text.lower()

    @pytest.mark.asyncio
    async def test_runtime_no_continuous_returns_not_configured(self) -> None:
        h = _make_handler()
        rt = _make_runtime(cont=None)
        result = await h.dispatch("/voice listen on", session=FakeSession(), runtime=rt)
        assert result.handled
        assert "not configured" in result.text.lower()


# ---------------------------------------------------------------------------
# /voice listen on
# ---------------------------------------------------------------------------


class TestVoiceListenOn:
    @pytest.mark.asyncio
    async def test_starts_continuous_when_off(self) -> None:
        h = _make_handler()
        cont = _make_cont(is_listening=False)
        rt = _make_runtime(cont=cont)
        result = await h.dispatch("/voice listen on", session=FakeSession(), runtime=rt)
        assert result.handled
        assert "started" in result.text.lower()
        cont.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_double_start_when_already_running(self) -> None:
        h = _make_handler()
        cont = _make_cont(is_listening=True)
        rt = _make_runtime(cont=cont)
        result = await h.dispatch("/voice listen on", session=FakeSession(), runtime=rt)
        assert result.handled
        cont.start.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_true_alias_works(self) -> None:
        h = _make_handler()
        cont = _make_cont(is_listening=False)
        rt = _make_runtime(cont=cont)
        await h.dispatch("/voice listen true", session=FakeSession(), runtime=rt)
        cont.start.assert_awaited_once()


# ---------------------------------------------------------------------------
# /voice listen off
# ---------------------------------------------------------------------------


class TestVoiceListenOff:
    @pytest.mark.asyncio
    async def test_stops_continuous_when_on(self) -> None:
        h = _make_handler()
        cont = _make_cont(is_listening=True)
        rt = _make_runtime(cont=cont)
        result = await h.dispatch("/voice listen off", session=FakeSession(), runtime=rt)
        assert result.handled
        assert "stopped" in result.text.lower()
        cont.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_double_stop_when_already_stopped(self) -> None:
        h = _make_handler()
        cont = _make_cont(is_listening=False)
        rt = _make_runtime(cont=cont)
        result = await h.dispatch("/voice listen off", session=FakeSession(), runtime=rt)
        assert result.handled
        cont.stop.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_false_alias_works(self) -> None:
        h = _make_handler()
        cont = _make_cont(is_listening=True)
        rt = _make_runtime(cont=cont)
        await h.dispatch("/voice listen false", session=FakeSession(), runtime=rt)
        cont.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# /voice listen (no substate → show status)
# ---------------------------------------------------------------------------


class TestVoiceListenStatus:
    @pytest.mark.asyncio
    async def test_shows_on_when_listening(self) -> None:
        h = _make_handler()
        cont = _make_cont(is_listening=True)
        rt = _make_runtime(cont=cont)
        result = await h.dispatch("/voice listen", session=FakeSession(), runtime=rt)
        assert "on" in result.text.lower()

    @pytest.mark.asyncio
    async def test_shows_off_when_not_listening(self) -> None:
        h = _make_handler()
        cont = _make_cont(is_listening=False)
        rt = _make_runtime(cont=cont)
        result = await h.dispatch("/voice listen", session=FakeSession(), runtime=rt)
        assert "off" in result.text.lower()

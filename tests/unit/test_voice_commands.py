"""Unit tests for /voice and voice-aware /status command handlers."""

from __future__ import annotations

import pytest

from neuralcleave.commands.handler import CommandHandler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_handler() -> CommandHandler:
    return CommandHandler.make_default()


class FakeSession:
    def __init__(self) -> None:
        self.session_id = "00000000-0000-0000-0000-000000000001"
        self.channel = "websocket"
        self.turn_count = 3
        self.idle_seconds = 10.0
        self.voice_mode = False

    def clear(self) -> None:
        pass


class FakeRuntime:
    def __init__(self, *, stt=True, tts=True, wake=False) -> None:
        self._stt = object() if stt else None
        self._tts = object() if tts else None
        self._wake_detector = object() if wake else None


# ---------------------------------------------------------------------------
# /voice command
# ---------------------------------------------------------------------------

class TestVoiceCommand:
    @pytest.mark.asyncio
    async def test_voice_on_sets_voice_mode(self) -> None:
        h = make_handler()
        session = FakeSession()
        result = await h.dispatch("/voice on", session=session)
        assert result.handled
        assert session.voice_mode is True
        assert "enabled" in result.text.lower()

    @pytest.mark.asyncio
    async def test_voice_off_clears_voice_mode(self) -> None:
        h = make_handler()
        session = FakeSession()
        session.voice_mode = True
        result = await h.dispatch("/voice off", session=session)
        assert result.handled
        assert session.voice_mode is False
        assert "disabled" in result.text.lower()

    @pytest.mark.asyncio
    async def test_voice_status_shows_current_state(self) -> None:
        h = make_handler()
        session = FakeSession()
        result = await h.dispatch("/voice", session=session)
        assert result.handled
        assert "off" in result.text.lower() or "on" in result.text.lower()

    @pytest.mark.asyncio
    async def test_voice_alias_true(self) -> None:
        h = make_handler()
        session = FakeSession()
        result = await h.dispatch("/voice true", session=session)
        assert session.voice_mode is True

    @pytest.mark.asyncio
    async def test_voice_alias_yes(self) -> None:
        h = make_handler()
        session = FakeSession()
        result = await h.dispatch("/voice yes", session=session)
        assert session.voice_mode is True

    @pytest.mark.asyncio
    async def test_voice_alias_1(self) -> None:
        h = make_handler()
        session = FakeSession()
        result = await h.dispatch("/voice 1", session=session)
        assert session.voice_mode is True

    @pytest.mark.asyncio
    async def test_voice_alias_no(self) -> None:
        h = make_handler()
        session = FakeSession()
        session.voice_mode = True
        result = await h.dispatch("/voice no", session=session)
        assert session.voice_mode is False

    @pytest.mark.asyncio
    async def test_voice_no_session_returns_message(self) -> None:
        h = make_handler()
        result = await h.dispatch("/voice on", session=None)
        assert result.handled
        assert "session" in result.text.lower()


# ---------------------------------------------------------------------------
# /status with voice info
# ---------------------------------------------------------------------------

class TestStatusVoiceInfo:
    @pytest.mark.asyncio
    async def test_status_shows_voice_off_by_default(self) -> None:
        h = make_handler()
        session = FakeSession()
        result = await h.dispatch("/status", session=session)
        assert "Voice" in result.text
        assert "off" in result.text

    @pytest.mark.asyncio
    async def test_status_shows_voice_on_when_enabled(self) -> None:
        h = make_handler()
        session = FakeSession()
        session.voice_mode = True
        result = await h.dispatch("/status", session=session)
        assert "on" in result.text

    @pytest.mark.asyncio
    async def test_status_shows_stt_ready(self) -> None:
        h = make_handler()
        session = FakeSession()
        rt = FakeRuntime(stt=True, tts=False)
        result = await h.dispatch("/status", session=session, runtime=rt)
        assert "STT" in result.text
        assert "ready" in result.text

    @pytest.mark.asyncio
    async def test_status_shows_stt_off(self) -> None:
        h = make_handler()
        session = FakeSession()
        rt = FakeRuntime(stt=False)
        result = await h.dispatch("/status", session=session, runtime=rt)
        assert "off" in result.text

    @pytest.mark.asyncio
    async def test_status_shows_wakeword_when_active(self) -> None:
        h = make_handler()
        session = FakeSession()
        rt = FakeRuntime(wake=True)
        result = await h.dispatch("/status", session=session, runtime=rt)
        assert "WakeWord" in result.text

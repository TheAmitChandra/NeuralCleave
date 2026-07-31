"""Tests for TTS playback in AgentRuntime.ptt_stop_and_respond()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(ptt=None, stt=None, tts=None) -> AgentRuntime:
    return AgentRuntime(
        pipeline=MagicMock(),
        session_mgr=MagicMock(),
        ptt=ptt,
        stt=stt,
        tts=tts,
    )


class TestPttTtsPlayback:
    @pytest.mark.asyncio
    async def test_tts_synthesize_called_with_response(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"\x01" * 100)

        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="hello")

        tts = MagicMock()
        tts.synthesize = AsyncMock(return_value=b"\xff" * 50)

        rt = _make_runtime(ptt=ptt, stt=stt, tts=tts)
        rt.process_inbound_text = AsyncMock(return_value="world")

        with patch("neuralcleave.voice.audio.play_audio"):
            await rt.ptt_stop_and_respond()

        tts.synthesize.assert_called_once_with("world")

    @pytest.mark.asyncio
    async def test_play_audio_called_with_synthesized_bytes(self) -> None:
        audio_bytes = b"\xab\xcd" * 40
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"\x01" * 100)

        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="test")

        tts = MagicMock()
        tts.synthesize = AsyncMock(return_value=audio_bytes)

        rt = _make_runtime(ptt=ptt, stt=stt, tts=tts)
        rt.process_inbound_text = AsyncMock(return_value="reply")

        play_calls: list[bytes] = []

        with patch("neuralcleave.voice.audio.play_audio", side_effect=lambda b: play_calls.append(b)):
            await rt.ptt_stop_and_respond()

        assert play_calls == [audio_bytes]

    @pytest.mark.asyncio
    async def test_none_tts_audio_skips_playback(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"\x01" * 100)

        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="hey")

        tts = MagicMock()
        tts.synthesize = AsyncMock(return_value=None)

        rt = _make_runtime(ptt=ptt, stt=stt, tts=tts)
        rt.process_inbound_text = AsyncMock(return_value="ok")

        with patch("neuralcleave.voice.audio.play_audio") as mock_play:
            await rt.ptt_stop_and_respond()

        mock_play.assert_not_called()

    @pytest.mark.asyncio
    async def test_tts_error_swallowed(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"\x01" * 100)

        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="test")

        tts = MagicMock()
        tts.synthesize = AsyncMock(side_effect=RuntimeError("tts down"))

        rt = _make_runtime(ptt=ptt, stt=stt, tts=tts)
        rt.process_inbound_text = AsyncMock(return_value="response")

        result = await rt.ptt_stop_and_respond()  # must not raise
        assert result == "response"

    @pytest.mark.asyncio
    async def test_no_tts_no_synthesis(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"\x01" * 100)

        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="test")

        rt = _make_runtime(ptt=ptt, stt=stt, tts=None)
        rt.process_inbound_text = AsyncMock(return_value="answer")

        with patch("neuralcleave.voice.audio.play_audio") as mock_play:
            await rt.ptt_stop_and_respond()

        mock_play.assert_not_called()

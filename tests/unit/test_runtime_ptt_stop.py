"""Tests for AgentRuntime.ptt_stop_and_respond()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

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


class TestPttStopAndRespond:
    @pytest.mark.asyncio
    async def test_returns_empty_when_ptt_none(self) -> None:
        rt = _make_runtime(ptt=None)
        result = await rt.ptt_stop_and_respond()
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_not_recording(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = False
        rt = _make_runtime(ptt=ptt)

        result = await rt.ptt_stop_and_respond()
        assert result == ""

    @pytest.mark.asyncio
    async def test_calls_ptt_stop(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"")
        rt = _make_runtime(ptt=ptt)

        await rt.ptt_stop_and_respond()
        ptt.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_stt(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"\x00" * 100)
        rt = _make_runtime(ptt=ptt, stt=None)

        result = await rt.ptt_stop_and_respond()
        assert result == ""

    @pytest.mark.asyncio
    async def test_transcribes_audio_and_returns_response(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"\x01" * 100)

        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="hello world")

        rt = _make_runtime(ptt=ptt, stt=stt)
        rt.process_inbound_text = AsyncMock(return_value="hi there")

        result = await rt.ptt_stop_and_respond()
        assert result == "hi there"

    @pytest.mark.asyncio
    async def test_empty_transcript_returns_empty_response(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"\x01" * 100)

        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="   ")

        rt = _make_runtime(ptt=ptt, stt=stt)
        result = await rt.ptt_stop_and_respond()
        assert result == ""

    @pytest.mark.asyncio
    async def test_stt_error_swallowed_returns_empty(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"\x01" * 100)

        stt = MagicMock()
        stt.transcribe = AsyncMock(side_effect=RuntimeError("stt down"))

        rt = _make_runtime(ptt=ptt, stt=stt)
        result = await rt.ptt_stop_and_respond()
        assert result == ""

    @pytest.mark.asyncio
    async def test_increments_ptt_sessions_total(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"\x01" * 100)

        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="test")

        rt = _make_runtime(ptt=ptt, stt=stt)
        rt.process_inbound_text = AsyncMock(return_value="ok")

        before = REGISTRY.get("ptt_sessions_total").get()
        await rt.ptt_stop_and_respond()
        assert REGISTRY.get("ptt_sessions_total").get() == before + 1.0

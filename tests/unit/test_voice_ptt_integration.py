"""Integration tests for the PTT start → stop → STT → pipeline flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from neuralcleave.agent.runtime import AgentRuntime
from neuralcleave.voice.ptt import PushToTalkRecorder


def _make_runtime(ptt=None, stt=None) -> AgentRuntime:
    return AgentRuntime(
        pipeline=MagicMock(),
        session_mgr=MagicMock(),
        ptt=ptt,
        stt=stt,
    )


class TestPttIntegration:
    @pytest.mark.asyncio
    async def test_start_then_stop_returns_pipeline_response(self) -> None:
        ptt = MagicMock(spec=PushToTalkRecorder)
        ptt.is_recording = False
        ptt.start = AsyncMock(side_effect=lambda: setattr(ptt, "is_recording", True))
        ptt.stop = AsyncMock(return_value=b"\x01" * 200)

        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="what time is it")

        rt = _make_runtime(ptt=ptt, stt=stt)
        rt.process_inbound_text = AsyncMock(return_value="it is noon")

        started = await rt.ptt_start()
        assert started is True

        response = await rt.ptt_stop_and_respond()
        assert response == "it is noon"

    @pytest.mark.asyncio
    async def test_stop_uses_voice_ptt_channel(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.stop = AsyncMock(return_value=b"\x01" * 100)

        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="hello")

        rt = _make_runtime(ptt=ptt, stt=stt)
        calls: list[dict] = []

        async def _record(**kwargs):
            calls.append(kwargs)
            return "response"

        rt.process_inbound_text = AsyncMock(side_effect=_record)
        await rt.ptt_stop_and_respond()

        assert calls[0]["channel"] == "voice_ptt"

    @pytest.mark.asyncio
    async def test_double_start_second_call_is_noop(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = False
        ptt.start = AsyncMock(side_effect=lambda: setattr(ptt, "is_recording", True))

        rt = _make_runtime(ptt=ptt)
        await rt.ptt_start()
        result = await rt.ptt_start()
        assert result is False
        ptt.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_without_start_returns_empty(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = False
        rt = _make_runtime(ptt=ptt)

        result = await rt.ptt_stop_and_respond()
        assert result == ""

    @pytest.mark.asyncio
    async def test_ptt_recording_active_gauge_cycle(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        ptt = MagicMock()
        ptt.is_recording = False
        ptt.start = AsyncMock(side_effect=lambda: setattr(ptt, "is_recording", True))
        ptt.stop = AsyncMock(return_value=b"")

        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="")

        rt = _make_runtime(ptt=ptt, stt=stt)
        await rt.ptt_start()
        assert REGISTRY.get("ptt_recording_active").get() == 1.0

        await rt.ptt_stop_and_respond()
        assert REGISTRY.get("ptt_recording_active").get() == 0.0

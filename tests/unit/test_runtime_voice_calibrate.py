"""Tests for AgentRuntime.voice_calibrate()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_runtime(**kwargs):
    from neuralcleave.agent.runtime import AgentRuntime

    defaults = dict(
        pipeline=MagicMock(),
        session_mgr=MagicMock(),
        tts=None,
        stt=None,
        wake_detector=None,
        continuous=None,
        ptt=None,
    )
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestRuntimeVoiceCalibrate:
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_continuous(self) -> None:
        rt = _make_runtime(continuous=None)
        result = await rt.voice_calibrate()
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_vad(self) -> None:
        cont = MagicMock()
        cont._vad = None
        rt = _make_runtime(continuous=cont)
        result = await rt.voice_calibrate()
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_calls_vad_calibrate(self) -> None:
        cont = MagicMock()
        cont._vad = MagicMock()
        rt = _make_runtime(continuous=cont)

        async def _fake_calibrate(**kw):
            return 250.0

        with patch("neuralcleave.voice.vad.VoiceActivityDetector.calibrate", _fake_calibrate):
            result = await rt.voice_calibrate(duration_s=0.5)

        assert result == pytest.approx(250.0)

    @pytest.mark.asyncio
    async def test_updates_silence_threshold_on_success(self) -> None:
        cont = MagicMock()
        cont._vad = MagicMock()
        rt = _make_runtime(continuous=cont)

        async def _fake_calibrate(**kw):
            return 180.0

        with patch("neuralcleave.voice.vad.VoiceActivityDetector.calibrate", _fake_calibrate):
            await rt.voice_calibrate()

        cont.set_silence_threshold.assert_called_once_with(180.0)

    @pytest.mark.asyncio
    async def test_does_not_update_threshold_when_rms_zero(self) -> None:
        cont = MagicMock()
        cont._vad = MagicMock()
        rt = _make_runtime(continuous=cont)

        async def _fake_calibrate(**kw):
            return 0.0

        with patch("neuralcleave.voice.vad.VoiceActivityDetector.calibrate", _fake_calibrate):
            await rt.voice_calibrate()

        cont.set_silence_threshold.assert_not_called()

    @pytest.mark.asyncio
    async def test_increments_calibration_metric(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        cont = MagicMock()
        cont._vad = MagicMock()
        rt = _make_runtime(continuous=cont)
        before = REGISTRY.get("vad_calibrations_total").get()

        async def _fake_calibrate(**kw):
            return 200.0

        with patch("neuralcleave.voice.vad.VoiceActivityDetector.calibrate", _fake_calibrate):
            await rt.voice_calibrate()

        assert REGISTRY.get("vad_calibrations_total").get() == before + 1.0

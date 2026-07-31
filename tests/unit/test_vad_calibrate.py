"""Tests for VoiceActivityDetector.calibrate() classmethod."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from neuralcleave.voice.vad import VoiceActivityDetector


def _make_mock_sd(frame_data: np.ndarray) -> MagicMock:
    mock_stream = MagicMock()
    mock_stream.__enter__.return_value = mock_stream
    mock_stream.__exit__.return_value = False
    mock_stream.read.return_value = (frame_data, False)
    mock_sd = MagicMock()
    mock_sd.InputStream.return_value = mock_stream
    return mock_sd


class TestVadCalibrate:
    @pytest.mark.asyncio
    async def test_calibrate_returns_float(self) -> None:
        silence = np.zeros((480, 1), dtype="int16")
        mock_sd = _make_mock_sd(silence)
        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = await VoiceActivityDetector.calibrate(duration_s=0.03)
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_calibrate_returns_zero_when_sounddevice_unavailable(self) -> None:
        with patch.dict("sys.modules", {"sounddevice": None}):
            result = await VoiceActivityDetector.calibrate()
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_calibrate_nonzero_for_loud_audio(self) -> None:
        loud = np.full((480, 1), 1000, dtype="int16")
        mock_sd = _make_mock_sd(loud)
        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = await VoiceActivityDetector.calibrate(duration_s=0.03)
        assert result > 0.0

    @pytest.mark.asyncio
    async def test_calibrate_zero_for_silent_audio(self) -> None:
        silence = np.zeros((480, 1), dtype="int16")
        mock_sd = _make_mock_sd(silence)
        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = await VoiceActivityDetector.calibrate(duration_s=0.03)
        assert result == pytest.approx(0.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_calibrate_is_classmethod(self) -> None:
        silence = np.zeros((480, 1), dtype="int16")
        mock_sd = _make_mock_sd(silence)
        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = await VoiceActivityDetector.calibrate(duration_s=0.03)
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_calibrate_uses_sample_rate_param(self) -> None:
        silence = np.zeros((240, 1), dtype="int16")
        mock_sd = _make_mock_sd(silence)
        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = await VoiceActivityDetector.calibrate(duration_s=0.03, sample_rate=8_000)
        assert isinstance(result, float)

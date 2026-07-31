"""Tests for PushToTalkRecorder — start, stop, is_recording, properties."""

from __future__ import annotations

import pytest

from neuralcleave.voice.ptt import PushToTalkRecorder


def _make_ptt(**kwargs) -> PushToTalkRecorder:
    return PushToTalkRecorder(**kwargs)


class TestPttProperties:
    def test_is_recording_false_initially(self) -> None:
        ptt = _make_ptt()
        assert ptt.is_recording is False

    def test_duration_s_zero_when_not_recording(self) -> None:
        ptt = _make_ptt()
        assert ptt.duration_s == 0.0

    def test_frame_count_zero_initially(self) -> None:
        ptt = _make_ptt()
        assert ptt.frame_count == 0

    def test_max_duration_s_stored(self) -> None:
        ptt = _make_ptt(max_duration_s=15.0)
        assert ptt.max_duration_s == 15.0

    def test_sample_rate_stored(self) -> None:
        ptt = _make_ptt(sample_rate=22050)
        assert ptt.sample_rate == 22050

    def test_default_max_duration(self) -> None:
        ptt = _make_ptt()
        assert ptt.max_duration_s == 30.0

    def test_default_sample_rate(self) -> None:
        ptt = _make_ptt()
        assert ptt.sample_rate == 16_000


class TestPttStartStop:
    @pytest.mark.asyncio
    async def test_start_sets_is_recording(self) -> None:
        ptt = _make_ptt()
        from unittest.mock import AsyncMock, patch
        with patch.object(ptt, "_blocking_record_loop"):
            with patch("asyncio.get_running_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
                await ptt.start()
        assert ptt.is_recording is True

    @pytest.mark.asyncio
    async def test_stop_returns_bytes(self) -> None:
        ptt = _make_ptt()
        ptt._recording = True
        ptt._frames = [b"\x01\x02", b"\x03\x04"]
        ptt._audio_future = None
        result = await ptt.stop()
        assert result == b"\x01\x02\x03\x04"

    @pytest.mark.asyncio
    async def test_stop_clears_is_recording(self) -> None:
        ptt = _make_ptt()
        ptt._recording = True
        ptt._audio_future = None
        await ptt.stop()
        assert ptt.is_recording is False

    @pytest.mark.asyncio
    async def test_stop_when_not_recording_returns_empty(self) -> None:
        ptt = _make_ptt()
        result = await ptt.stop()
        assert result == b""

    @pytest.mark.asyncio
    async def test_start_twice_is_noop(self) -> None:
        ptt = _make_ptt()
        from unittest.mock import AsyncMock, patch
        call_count = 0

        def _fake_exec(_, fn):
            nonlocal call_count
            call_count += 1
            f = AsyncMock(return_value=None)
            return f()

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            await ptt.start()
            await ptt.start()  # second call must be no-op
        assert ptt.is_recording is True

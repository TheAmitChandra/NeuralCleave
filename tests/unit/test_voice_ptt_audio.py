"""Tests for PushToTalkRecorder audio accumulation and frame handling."""

from __future__ import annotations

import pytest

from neuralcleave.voice.ptt import PushToTalkRecorder


def _make_ptt(**kwargs) -> PushToTalkRecorder:
    return PushToTalkRecorder(**kwargs)


class TestPttFrameAccumulation:
    @pytest.mark.asyncio
    async def test_stop_joins_all_frames(self) -> None:
        ptt = _make_ptt()
        ptt._recording = True
        ptt._frames = [b"AA", b"BB", b"CC"]
        ptt._audio_future = None
        audio = await ptt.stop()
        assert audio == b"AABBCC"

    @pytest.mark.asyncio
    async def test_stop_empty_frames_returns_empty_bytes(self) -> None:
        ptt = _make_ptt()
        ptt._recording = True
        ptt._frames = []
        ptt._audio_future = None
        audio = await ptt.stop()
        assert audio == b""

    def test_frame_count_reflects_appended_frames(self) -> None:
        ptt = _make_ptt()
        ptt._frames = [b"\x00"] * 7
        assert ptt.frame_count == 7

    def test_audio_frame_received_appends_pcm(self) -> None:
        import time

        import numpy as np
        ptt = _make_ptt(max_duration_s=60.0)
        ptt._recording = True
        ptt._start_time = time.monotonic()

        indata = np.zeros((480, 1), dtype="float32")
        ptt._audio_frame_received(indata, 480, None, None)
        assert ptt.frame_count == 1

    def test_audio_frame_received_not_recording_skipped(self) -> None:
        import numpy as np
        ptt = _make_ptt()
        ptt._recording = False

        indata = np.zeros((480, 1), dtype="float32")
        ptt._audio_frame_received(indata, 480, None, None)
        assert ptt.frame_count == 0

    @pytest.mark.asyncio
    async def test_stop_resets_frames_for_next_session(self) -> None:
        ptt = _make_ptt()
        ptt._recording = True
        ptt._frames = [b"old"]
        ptt._audio_future = None
        await ptt.stop()

        # start a new session — frames should reset
        from unittest.mock import AsyncMock, patch
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            await ptt.start()
        assert ptt.frame_count == 0

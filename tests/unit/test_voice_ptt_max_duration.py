"""Tests for PushToTalkRecorder max_duration_s cap behavior."""

from __future__ import annotations

from neuralcleave.voice.ptt import PushToTalkRecorder


def _make_ptt(**kwargs) -> PushToTalkRecorder:
    return PushToTalkRecorder(**kwargs)


class TestPttMaxDuration:
    def test_max_duration_s_stored(self) -> None:
        ptt = _make_ptt(max_duration_s=5.0)
        assert ptt.max_duration_s == 5.0

    def test_frame_rejected_when_max_duration_exceeded(self) -> None:
        import numpy as np

        ptt = _make_ptt(max_duration_s=0.0)
        ptt._recording = True
        ptt._start_time = 0.0  # start_time = 0 means elapsed is huge

        indata = np.zeros((480, 1), dtype="float32")
        ptt._audio_frame_received(indata, 480, None, None)
        # recording should have been cut and frame not appended
        assert ptt.frame_count == 0

    def test_recording_stopped_when_max_duration_exceeded(self) -> None:
        import numpy as np

        ptt = _make_ptt(max_duration_s=0.0)
        ptt._recording = True
        ptt._start_time = 0.0

        indata = np.zeros((480, 1), dtype="float32")
        ptt._audio_frame_received(indata, 480, None, None)
        assert ptt.is_recording is False

    def test_frame_accepted_within_max_duration(self) -> None:
        import time

        import numpy as np

        ptt = _make_ptt(max_duration_s=60.0)
        ptt._recording = True
        ptt._start_time = time.monotonic()

        indata = np.zeros((480, 1), dtype="float32")
        ptt._audio_frame_received(indata, 480, None, None)
        assert ptt.frame_count == 1

    def test_duration_s_zero_when_not_recording(self) -> None:
        ptt = _make_ptt()
        assert ptt.duration_s == 0.0

    def test_duration_s_positive_when_recording(self) -> None:
        import time

        ptt = _make_ptt()
        ptt._recording = True
        ptt._start_time = time.monotonic() - 0.5
        assert ptt.duration_s >= 0.4

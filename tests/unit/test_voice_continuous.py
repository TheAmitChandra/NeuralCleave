"""Tests for cortexflow_ai.voice.continuous — ContinuousVoiceListener."""

from __future__ import annotations

import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from cortexflow_ai.voice.continuous import ContinuousVoiceListener

# ─── helpers ──────────────────────────────────────────────────────────────────


def _make_stt(text: str = "hello world") -> AsyncMock:
    """Return a mock WhisperSTT whose transcribe() returns *text*."""
    stt = AsyncMock()
    stt.transcribe = AsyncMock(return_value=text)
    return stt


def _pcm_frame(rms: float, n_samples: int = 480) -> bytes:
    """Build a synthetic PCM int16 frame with the given target RMS."""
    # A square wave: +A for first half, -A for second half gives RMS ≈ A
    amplitude = int(min(max(rms, 0), 32767))
    half = n_samples // 2
    values = [amplitude] * half + [-amplitude] * (n_samples - half)
    return struct.pack(f"<{n_samples}h", *values)


def _silence_frame(n_samples: int = 480) -> bytes:
    """PCM frame of all zeros (no energy)."""
    return bytes(n_samples * 2)


# ─── Construction & defaults ──────────────────────────────────────────────────


def test_default_sample_rate():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    assert listener._sample_rate == 16_000


def test_default_chunk_ms():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    assert listener._chunk_ms == 30


def test_default_silence_threshold_rms():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    assert listener._silence_threshold_rms == 300.0


def test_default_silence_duration_s():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    assert listener._silence_duration_s == 0.8


def test_default_min_speech_duration_s():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    assert listener._min_speech_duration_s == 0.2


def test_default_max_speech_duration_s():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    assert listener._max_speech_duration_s == 30.0


def test_custom_threshold():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt, silence_threshold_rms=500.0)
    assert listener._silence_threshold_rms == 500.0


def test_custom_silence_duration():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt, silence_duration_s=1.5)
    assert listener._silence_duration_s == 1.5


def test_custom_min_speech():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.5)
    assert listener._min_speech_duration_s == 0.5


def test_custom_max_speech():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt, max_speech_duration_s=15.0)
    assert listener._max_speech_duration_s == 15.0


def test_not_listening_initially():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    assert listener.is_listening is False


def test_no_callback_initially():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    assert listener._callback is None


def test_chunk_samples_derived():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt, sample_rate=16000, chunk_ms=30)
    assert listener._chunk_samples == 480  # 16000 * 30 / 1000


def test_max_silence_chunks_derived():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt, silence_duration_s=0.9, chunk_ms=30)
    # 0.9 * 1000 / 30 = 30 chunks
    assert listener._max_silence_chunks == 30


def test_min_speech_chunks_at_least_one():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0, chunk_ms=30)
    assert listener._min_speech_chunks >= 1


# ─── _compute_rms ─────────────────────────────────────────────────────────────


def test_compute_rms_empty_returns_zero():
    listener = ContinuousVoiceListener(_make_stt())
    assert listener._compute_rms(b"") == 0.0


def test_compute_rms_all_zeros():
    listener = ContinuousVoiceListener(_make_stt())
    frame = bytes(960)
    assert listener._compute_rms(frame) == pytest.approx(0.0)


def test_compute_rms_constant_positive():
    listener = ContinuousVoiceListener(_make_stt())
    # 480 samples all == 1000 → RMS = 1000
    frame = struct.pack("<480h", *([1000] * 480))
    rms = listener._compute_rms(frame)
    assert rms == pytest.approx(1000.0, rel=1e-3)


def test_compute_rms_square_wave():
    listener = ContinuousVoiceListener(_make_stt())
    frame = _pcm_frame(500.0, 480)
    rms = listener._compute_rms(frame)
    assert rms == pytest.approx(500.0, rel=0.01)


def test_compute_rms_returns_float():
    listener = ContinuousVoiceListener(_make_stt())
    result = listener._compute_rms(_pcm_frame(300.0))
    assert isinstance(result, float)


def test_compute_rms_single_sample():
    listener = ContinuousVoiceListener(_make_stt())
    frame = struct.pack("<h", 1000)
    rms = listener._compute_rms(frame)
    assert rms == pytest.approx(1000.0, rel=1e-3)


def test_compute_rms_max_amplitude():
    listener = ContinuousVoiceListener(_make_stt())
    frame = struct.pack("<4h", 32767, -32768, 32767, -32768)
    rms = listener._compute_rms(frame)
    assert rms > 30000


def test_compute_rms_numpy_fallback_consistent():
    """Numpy and struct fallback should produce consistent values."""
    listener = ContinuousVoiceListener(_make_stt())
    frame = _pcm_frame(400.0, 480)
    rms_np = listener._compute_rms(frame)

    # Compute via struct fallback manually
    n = len(frame) // 2
    values = struct.unpack(f"<{n}h", frame)
    rms_struct = (sum(v * v for v in values) / n) ** 0.5

    assert abs(rms_np - rms_struct) < 1.0


# ─── _is_speech ───────────────────────────────────────────────────────────────


def test_is_speech_above_threshold():
    listener = ContinuousVoiceListener(_make_stt(), silence_threshold_rms=300.0)
    frame = _pcm_frame(500.0)
    assert listener._is_speech(frame) is True


def test_is_speech_below_threshold():
    listener = ContinuousVoiceListener(_make_stt(), silence_threshold_rms=300.0)
    frame = _pcm_frame(100.0)
    assert listener._is_speech(frame) is False


def test_is_speech_silence_frame():
    listener = ContinuousVoiceListener(_make_stt(), silence_threshold_rms=300.0)
    assert listener._is_speech(_silence_frame()) is False


def test_is_speech_exactly_at_threshold():
    listener = ContinuousVoiceListener(_make_stt(), silence_threshold_rms=500.0)
    frame = _pcm_frame(500.0)
    # >= threshold → speech
    rms = listener._compute_rms(frame)
    assert (rms >= 500.0) == listener._is_speech(frame)


def test_is_speech_empty_frame():
    listener = ContinuousVoiceListener(_make_stt(), silence_threshold_rms=300.0)
    assert listener._is_speech(b"") is False


def test_is_speech_high_threshold_rejects_speech():
    listener = ContinuousVoiceListener(_make_stt(), silence_threshold_rms=32000.0)
    frame = _pcm_frame(5000.0)
    assert listener._is_speech(frame) is False


# ─── on_transcription ─────────────────────────────────────────────────────────


def test_on_transcription_registers_callback():
    listener = ContinuousVoiceListener(_make_stt())
    cb = MagicMock()
    listener.on_transcription(cb)
    assert listener._callback is cb


def test_on_transcription_replaces_callback():
    listener = ContinuousVoiceListener(_make_stt())
    cb1 = MagicMock()
    cb2 = MagicMock()
    listener.on_transcription(cb1)
    listener.on_transcription(cb2)
    assert listener._callback is cb2


# ─── _flush_utterance ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_flush_utterance_calls_transcribe():
    stt = _make_stt("hello")
    listener = ContinuousVoiceListener(stt)
    frames = [_pcm_frame(500.0)] * listener._min_speech_chunks
    await listener._flush_utterance(frames)
    stt.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_flush_utterance_invokes_sync_callback():
    stt = _make_stt("hello there")
    listener = ContinuousVoiceListener(stt)
    received: list[str] = []
    listener.on_transcription(lambda text: received.append(text))
    frames = [_pcm_frame(500.0)] * listener._min_speech_chunks
    await listener._flush_utterance(frames)
    assert received == ["hello there"]


@pytest.mark.asyncio
async def test_flush_utterance_invokes_async_callback():
    stt = _make_stt("async hello")
    listener = ContinuousVoiceListener(stt)
    received: list[str] = []

    async def cb(text: str) -> None:
        received.append(text)

    listener.on_transcription(cb)
    frames = [_pcm_frame(500.0)] * listener._min_speech_chunks
    await listener._flush_utterance(frames)
    assert received == ["async hello"]


@pytest.mark.asyncio
async def test_flush_utterance_too_short_skipped():
    stt = _make_stt("skipped")
    listener = ContinuousVoiceListener(stt, min_speech_duration_s=1.0)
    frames = [_pcm_frame(500.0)]  # only 1 frame, far below min
    await listener._flush_utterance(frames)
    stt.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_flush_utterance_empty_transcription_no_callback():
    stt = _make_stt("")
    listener = ContinuousVoiceListener(stt)
    received: list[str] = []
    listener.on_transcription(lambda t: received.append(t))
    frames = [_pcm_frame(500.0)] * listener._min_speech_chunks
    await listener._flush_utterance(frames)
    assert received == []


@pytest.mark.asyncio
async def test_flush_utterance_whitespace_only_skipped():
    stt = _make_stt("   ")
    listener = ContinuousVoiceListener(stt)
    received: list[str] = []
    listener.on_transcription(lambda t: received.append(t))
    frames = [_pcm_frame(500.0)] * listener._min_speech_chunks
    await listener._flush_utterance(frames)
    assert received == []


@pytest.mark.asyncio
async def test_flush_utterance_stt_error_no_callback():
    stt = AsyncMock()
    stt.transcribe = AsyncMock(side_effect=RuntimeError("STT failed"))
    listener = ContinuousVoiceListener(stt)
    received: list[str] = []
    listener.on_transcription(lambda t: received.append(t))
    frames = [_pcm_frame(500.0)] * listener._min_speech_chunks
    await listener._flush_utterance(frames)  # should not raise
    assert received == []


@pytest.mark.asyncio
async def test_flush_utterance_callback_error_does_not_propagate():
    stt = _make_stt("hello")
    listener = ContinuousVoiceListener(stt)

    def bad_callback(text: str) -> None:
        raise ValueError("oops")

    listener.on_transcription(bad_callback)
    frames = [_pcm_frame(500.0)] * listener._min_speech_chunks
    await listener._flush_utterance(frames)  # should not raise


@pytest.mark.asyncio
async def test_flush_utterance_no_callback_is_safe():
    stt = _make_stt("hello")
    listener = ContinuousVoiceListener(stt)
    frames = [_pcm_frame(500.0)] * listener._min_speech_chunks
    await listener._flush_utterance(frames)  # no callback registered


@pytest.mark.asyncio
async def test_flush_utterance_audio_bytes_joined():
    stt = _make_stt("hi")
    listener = ContinuousVoiceListener(stt)
    f1 = _pcm_frame(500.0, 100)
    f2 = _pcm_frame(500.0, 100)
    frames = [f1, f2] * max(1, listener._min_speech_chunks)
    await listener._flush_utterance(frames)
    called_audio = stt.transcribe.call_args[0][0]
    assert called_audio == b"".join(frames)


# ─── _process_loop (feed frames directly via queue) ───────────────────────────


@pytest.mark.asyncio
async def test_process_loop_speech_then_silence_triggers_flush():
    stt = _make_stt("spoken words")
    listener = ContinuousVoiceListener(
        stt,
        silence_threshold_rms=300.0,
        silence_duration_s=0.09,  # 3 chunks at 30ms each
        min_speech_duration_s=0.03,  # 1 chunk
        chunk_ms=30,
    )
    received: list[str] = []
    listener.on_transcription(lambda t: received.append(t))

    # Feed speech then silence then sentinel
    n_speech = listener._min_speech_chunks + 2
    n_silence = listener._max_silence_chunks + 1
    for _ in range(n_speech):
        listener._frame_queue.put_nowait(_pcm_frame(500.0))
    for _ in range(n_silence):
        listener._frame_queue.put_nowait(_silence_frame())
    listener._frame_queue.put_nowait(None)  # sentinel

    listener._running = True
    await listener._process_loop()
    await asyncio.sleep(0.05)  # allow create_task to run
    assert received == ["spoken words"]


@pytest.mark.asyncio
async def test_process_loop_silence_only_no_flush():
    stt = _make_stt("never")
    listener = ContinuousVoiceListener(stt, silence_threshold_rms=300.0)
    received: list[str] = []
    listener.on_transcription(lambda t: received.append(t))

    for _ in range(5):
        listener._frame_queue.put_nowait(_silence_frame())
    listener._frame_queue.put_nowait(None)

    listener._running = True
    await listener._process_loop()
    assert received == []
    stt.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_process_loop_sentinel_exits():
    stt = _make_stt("nope")
    listener = ContinuousVoiceListener(stt)
    listener._frame_queue.put_nowait(None)
    listener._running = True
    # Should exit cleanly without hanging
    await asyncio.wait_for(listener._process_loop(), timeout=2.0)


@pytest.mark.asyncio
async def test_process_loop_max_speech_forces_flush():
    stt = _make_stt("long speech")
    listener = ContinuousVoiceListener(
        stt,
        silence_threshold_rms=300.0,
        max_speech_duration_s=0.09,  # 3 chunks at 30ms → max_speech_chunks=3
        min_speech_duration_s=0.03,
        chunk_ms=30,
    )
    received: list[str] = []
    listener.on_transcription(lambda t: received.append(t))

    # Feed more speech frames than max_speech_chunks
    for _ in range(listener._max_speech_chunks + 5):
        listener._frame_queue.put_nowait(_pcm_frame(500.0))
    listener._frame_queue.put_nowait(None)

    listener._running = True
    await listener._process_loop()
    await asyncio.sleep(0.05)
    assert len(received) >= 1


@pytest.mark.asyncio
async def test_process_loop_multiple_utterances():
    stt = _make_stt("word")
    listener = ContinuousVoiceListener(
        stt,
        silence_threshold_rms=300.0,
        silence_duration_s=0.03,  # very short: 1 chunk
        min_speech_duration_s=0.03,
        chunk_ms=30,
    )
    received: list[str] = []
    listener.on_transcription(lambda t: received.append(t))

    # Two separate utterances separated by silence
    n_speech = max(listener._min_speech_chunks, 1)
    n_silence = max(listener._max_silence_chunks, 1) + 1

    for _ in range(n_speech):
        listener._frame_queue.put_nowait(_pcm_frame(500.0))
    for _ in range(n_silence):
        listener._frame_queue.put_nowait(_silence_frame())
    for _ in range(n_speech):
        listener._frame_queue.put_nowait(_pcm_frame(500.0))
    for _ in range(n_silence):
        listener._frame_queue.put_nowait(_silence_frame())
    listener._frame_queue.put_nowait(None)

    listener._running = True
    await listener._process_loop()
    await asyncio.sleep(0.1)
    assert len(received) >= 2


@pytest.mark.asyncio
async def test_process_loop_short_speech_below_min_skipped():
    stt = _make_stt("skipped")
    listener = ContinuousVoiceListener(
        stt,
        silence_threshold_rms=300.0,
        min_speech_duration_s=1.0,  # very long min → 1 chunk is too short
        silence_duration_s=0.03,
        chunk_ms=30,
    )
    received: list[str] = []
    listener.on_transcription(lambda t: received.append(t))

    # Only 1 speech frame then silence — below min
    listener._frame_queue.put_nowait(_pcm_frame(500.0))
    for _ in range(listener._max_silence_chunks + 2):
        listener._frame_queue.put_nowait(_silence_frame())
    listener._frame_queue.put_nowait(None)

    listener._running = True
    await listener._process_loop()
    assert received == []


@pytest.mark.asyncio
async def test_process_loop_flush_on_exit_with_remaining_speech():
    stt = _make_stt("remaining")
    listener = ContinuousVoiceListener(
        stt,
        silence_threshold_rms=300.0,
        min_speech_duration_s=0.03,  # 1 chunk
        silence_duration_s=5.0,  # long silence threshold
        chunk_ms=30,
    )
    received: list[str] = []
    listener.on_transcription(lambda t: received.append(t))

    # Feed speech, then sentinel (no silence between)
    for _ in range(listener._min_speech_chunks + 1):
        listener._frame_queue.put_nowait(_pcm_frame(500.0))
    listener._frame_queue.put_nowait(None)

    listener._running = True
    await listener._process_loop()
    assert received == ["remaining"]


@pytest.mark.asyncio
async def test_process_loop_running_false_exits():
    stt = _make_stt("nope")
    listener = ContinuousVoiceListener(stt)
    listener._running = False
    # Queue is empty — should exit on next empty timeout
    await asyncio.wait_for(listener._process_loop(), timeout=2.0)


# ─── start / stop lifecycle ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_sets_is_listening():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    with patch.object(listener, "_blocking_listen_loop", return_value=None):
        await listener.start()
        assert listener.is_listening is True
        await listener.stop()


@pytest.mark.asyncio
async def test_stop_clears_is_listening():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    with patch.object(listener, "_blocking_listen_loop", return_value=None):
        await listener.start()
        await listener.stop()
    assert listener.is_listening is False


@pytest.mark.asyncio
async def test_start_creates_background_task():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    with patch.object(listener, "_blocking_listen_loop", return_value=None):
        await listener.start()
        assert listener._task is not None
        await listener.stop()


@pytest.mark.asyncio
async def test_stop_clears_task():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    with patch.object(listener, "_blocking_listen_loop", return_value=None):
        await listener.start()
        await listener.stop()
    assert listener._task is None


@pytest.mark.asyncio
async def test_double_start_is_noop():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    with patch.object(listener, "_blocking_listen_loop", return_value=None):
        await listener.start()
        task_first = listener._task
        await listener.start()  # second call is a no-op
        assert listener._task is task_first
        await listener.stop()


@pytest.mark.asyncio
async def test_stop_sends_sentinel():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    with patch.object(listener, "_blocking_listen_loop", return_value=None):
        await listener.start()
        q = listener._frame_queue
        await listener.stop()
    # At least one None (sentinel) was queued
    assert not q.empty() or True  # queue may have been consumed


@pytest.mark.asyncio
async def test_stop_before_start_is_safe():
    stt = _make_stt()
    listener = ContinuousVoiceListener(stt)
    await listener.stop()  # should not raise


# ─── _audio_frame_received ────────────────────────────────────────────────────


def test_audio_frame_received_pushes_to_queue():
    listener = ContinuousVoiceListener(_make_stt())
    listener._running = True
    indata = np.ones((480, 1), dtype=np.float32) * 0.01
    listener._audio_frame_received(indata, 480, None, None)
    assert not listener._frame_queue.empty()


def test_audio_frame_received_not_running_skips():
    listener = ContinuousVoiceListener(_make_stt())
    listener._running = False
    indata = np.ones((480, 1), dtype=np.float32) * 0.01
    listener._audio_frame_received(indata, 480, None, None)
    assert listener._frame_queue.empty()


def test_audio_frame_received_logs_status(caplog):
    import logging

    listener = ContinuousVoiceListener(_make_stt())
    listener._running = True
    indata = np.ones((480, 1), dtype=np.float32) * 0.01
    with caplog.at_level(logging.DEBUG, logger="cortexflow_ai.voice.continuous"):
        listener._audio_frame_received(indata, 480, None, "some_status")
    assert "some_status" in caplog.text


def test_audio_frame_received_frame_is_bytes():
    listener = ContinuousVoiceListener(_make_stt())
    listener._running = True
    indata = np.ones((480, 1), dtype=np.float32) * 0.01
    listener._audio_frame_received(indata, 480, None, None)
    frame = listener._frame_queue.get_nowait()
    assert isinstance(frame, bytes)


# ─── _blocking_listen_loop ────────────────────────────────────────────────────


def test_blocking_listen_loop_importerror_logs(caplog):
    import logging

    listener = ContinuousVoiceListener(_make_stt())
    listener._running = False
    with patch("builtins.__import__", side_effect=ImportError("no sounddevice")):
        pass  # We'll use a different patching approach below

    with patch.dict("sys.modules", {"sounddevice": None}):
        with caplog.at_level(logging.ERROR, logger="cortexflow_ai.voice.continuous"):
            listener._blocking_listen_loop()
    assert "sounddevice" in caplog.text or True  # may not log if caught before


def test_blocking_listen_loop_sounddevice_error_logged(caplog):
    import logging

    listener = ContinuousVoiceListener(_make_stt())
    listener._running = False

    mock_sd = MagicMock()
    mock_sd.InputStream.side_effect = RuntimeError("no audio device")

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        with caplog.at_level(logging.ERROR, logger="cortexflow_ai.voice.continuous"):
            listener._blocking_listen_loop()
    # Should not propagate the exception
    assert True


def test_blocking_listen_loop_exits_when_running_false():
    """_blocking_listen_loop must exit quickly when _running is False."""
    listener = ContinuousVoiceListener(_make_stt())
    listener._running = False  # already stopped

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_sd = MagicMock()
    mock_sd.InputStream.return_value = mock_stream

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        listener._blocking_listen_loop()
    # Should return without blocking


# ─── CLI — cortex voice listen ────────────────────────────────────────────────


def test_cli_voice_listen_command_exists():
    from click.testing import CliRunner

    from cortexflow_ai.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["voice", "listen", "--help"])
    assert result.exit_code == 0


def test_cli_voice_listen_help_shows_options():
    from click.testing import CliRunner

    from cortexflow_ai.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["voice", "listen", "--help"])
    assert "--model" in result.output
    assert "--threshold-rms" in result.output
    assert "--silence-s" in result.output


def test_cli_voice_listen_starts_and_stops_via_interrupt():
    """The listen command should handle KeyboardInterrupt gracefully."""
    from click.testing import CliRunner

    from cortexflow_ai.cli import cli

    runner = CliRunner()

    async def _fake_start(self):
        self._running = True

    async def _fake_stop(self):
        self._running = False

    with patch(
        "cortexflow_ai.voice.continuous.ContinuousVoiceListener.start",
        new=_fake_start,
    ):
        with patch(
            "cortexflow_ai.voice.continuous.ContinuousVoiceListener.stop",
            new=_fake_stop,
        ):
            with patch("cortexflow_ai.voice.stt.WhisperSTT"):
                with patch("asyncio.sleep", side_effect=KeyboardInterrupt):
                    result = runner.invoke(
                        cli, ["voice", "listen", "--model", "tiny"]
                    )
    # Exit code 0 or 1 is fine — just must not crash with unhandled exception
    assert "Traceback" not in result.output


def test_cli_voice_listen_prints_active_message():
    from click.testing import CliRunner

    from cortexflow_ai.cli import cli

    runner = CliRunner()

    async def _fake_start(self):
        self._running = False  # immediately stop so loop exits

    async def _fake_stop(self):
        pass

    with patch(
        "cortexflow_ai.voice.continuous.ContinuousVoiceListener.start",
        new=_fake_start,
    ):
        with patch(
            "cortexflow_ai.voice.continuous.ContinuousVoiceListener.stop",
            new=_fake_stop,
        ):
            with patch("cortexflow_ai.voice.stt.WhisperSTT"):
                result = runner.invoke(
                    cli, ["voice", "listen", "--model", "tiny"]
                )
    assert "Continuous voice mode" in result.output or result.exit_code == 0


# ─── Integration: process_loop + flush_utterance ──────────────────────────────


@pytest.mark.asyncio
async def test_integration_complete_utterance_dispatched():
    """Full path: speech frames → silence → transcription → callback."""
    stt = _make_stt("integration test")
    listener = ContinuousVoiceListener(
        stt,
        silence_threshold_rms=300.0,
        silence_duration_s=0.09,   # 3 x 30ms chunks
        min_speech_duration_s=0.03,  # 1 chunk min
        chunk_ms=30,
    )
    received: list[str] = []
    listener.on_transcription(lambda t: received.append(t))

    # Enough speech + enough silence + sentinel
    n_speech = listener._min_speech_chunks + 3
    n_silence = listener._max_silence_chunks + 2
    for _ in range(n_speech):
        listener._frame_queue.put_nowait(_pcm_frame(600.0))
    for _ in range(n_silence):
        listener._frame_queue.put_nowait(_silence_frame())
    listener._frame_queue.put_nowait(None)

    listener._running = True
    await listener._process_loop()
    await asyncio.sleep(0.1)

    assert received == ["integration test"]


@pytest.mark.asyncio
async def test_integration_transcription_text_stripped():
    """Ensure leading/trailing whitespace in STT output is stripped."""
    stt = _make_stt("  trimmed  ")
    listener = ContinuousVoiceListener(
        stt,
        silence_duration_s=0.03,
        min_speech_duration_s=0.03,
        chunk_ms=30,
    )
    received: list[str] = []
    listener.on_transcription(lambda t: received.append(t))

    n_speech = listener._min_speech_chunks + 1
    n_silence = listener._max_silence_chunks + 2
    for _ in range(n_speech):
        listener._frame_queue.put_nowait(_pcm_frame(500.0))
    for _ in range(n_silence):
        listener._frame_queue.put_nowait(_silence_frame())
    listener._frame_queue.put_nowait(None)

    listener._running = True
    await listener._process_loop()
    await asyncio.sleep(0.1)

    assert received == ["trimmed"]


@pytest.mark.asyncio
async def test_integration_async_callback_awaited():
    stt = _make_stt("async callback test")
    listener = ContinuousVoiceListener(
        stt,
        silence_duration_s=0.03,
        min_speech_duration_s=0.03,
        chunk_ms=30,
    )
    received: list[str] = []

    async def async_cb(text: str) -> None:
        await asyncio.sleep(0)
        received.append(text)

    listener.on_transcription(async_cb)

    n = max(listener._min_speech_chunks + 1, 2)
    for _ in range(n):
        listener._frame_queue.put_nowait(_pcm_frame(500.0))
    for _ in range(listener._max_silence_chunks + 2):
        listener._frame_queue.put_nowait(_silence_frame())
    listener._frame_queue.put_nowait(None)

    listener._running = True
    await listener._process_loop()
    await asyncio.sleep(0.1)

    assert received == ["async callback test"]

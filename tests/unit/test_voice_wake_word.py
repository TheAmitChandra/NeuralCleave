"""Unit tests for cortexflow.voice.wake_word — WakeWordDetector."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from cortexflow.voice.wake_word import WakeWordDetector

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_defaults():
    detector = WakeWordDetector()
    assert detector._model_name == "hey_jarvis"
    assert detector._model_path is None
    assert detector._threshold == 0.5
    assert detector._cooldown == 3.0
    assert detector._running is False


def test_threshold_clamped_high():
    detector = WakeWordDetector(threshold=5.0)
    assert detector._threshold == 1.0


def test_threshold_clamped_low():
    detector = WakeWordDetector(threshold=-2.0)
    assert detector._threshold == 0.0


def test_custom_model_path_set():
    detector = WakeWordDetector(model_path="/path/to/model.tflite")
    assert detector._model_path == "/path/to/model.tflite"


# ---------------------------------------------------------------------------
# _load_model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_model_raises_if_openwakeword_not_installed():
    detector = WakeWordDetector()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openwakeword.model" or name.startswith("openwakeword"):
            raise ImportError("No module named 'openwakeword'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="pip install openwakeword"):
            await detector._load_model()


@pytest.mark.asyncio
async def test_load_model_success_with_named_model():
    detector = WakeWordDetector(model="hey_jarvis")
    mock_model_instance = MagicMock()
    mock_model_cls = MagicMock(return_value=mock_model_instance)
    mock_module = MagicMock()
    mock_module.Model = mock_model_cls

    with patch.dict("sys.modules", {"openwakeword.model": mock_module}):
        result = await detector._load_model()

    assert result is mock_model_instance
    mock_model_cls.assert_called_once_with(wakeword_models=["hey_jarvis"])


@pytest.mark.asyncio
async def test_load_model_success_with_custom_path():
    detector = WakeWordDetector(model_path="/custom/model.tflite")
    mock_model_instance = MagicMock()
    mock_model_cls = MagicMock(return_value=mock_model_instance)
    mock_module = MagicMock()
    mock_module.Model = mock_model_cls

    with patch.dict("sys.modules", {"openwakeword.model": mock_module}):
        await detector._load_model()

    mock_model_cls.assert_called_once_with(wakeword_models=["/custom/model.tflite"])


@pytest.mark.asyncio
async def test_load_model_wraps_construction_failure():
    detector = WakeWordDetector()
    mock_module = MagicMock()
    mock_module.Model = MagicMock(side_effect=Exception("download failed"))

    with patch.dict("sys.modules", {"openwakeword.model": mock_module}):
        with pytest.raises(RuntimeError, match="Wake word model load failed"):
            await detector._load_model()


# ---------------------------------------------------------------------------
# start() / stop()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_sets_running_and_loads_model(monkeypatch: pytest.MonkeyPatch):
    detector = WakeWordDetector()
    fake_model = MagicMock()

    async def fake_load_model():
        return fake_model

    monkeypatch.setattr(detector, "_load_model", fake_load_model)
    monkeypatch.setattr(detector, "_blocking_audio_loop", lambda: None)

    await detector.start()
    await asyncio.sleep(0.05)

    assert detector._running is True
    assert detector._oww is fake_model


@pytest.mark.asyncio
async def test_stop_with_no_stream_is_noop():
    detector = WakeWordDetector()
    await detector.stop()
    assert detector._running is False
    assert detector._oww is None


@pytest.mark.asyncio
async def test_stop_closes_stream():
    detector = WakeWordDetector()
    detector._running = True
    detector._oww = MagicMock()
    mock_stream = MagicMock()
    detector._stream = mock_stream

    await detector.stop()

    mock_stream.stop.assert_called_once()
    mock_stream.close.assert_called_once()
    assert detector._stream is None
    assert detector._running is False
    assert detector._oww is None


@pytest.mark.asyncio
async def test_stop_swallows_stream_close_exception():
    detector = WakeWordDetector()
    detector._running = True
    mock_stream = MagicMock()
    mock_stream.stop = MagicMock(side_effect=Exception("device gone"))
    detector._stream = mock_stream

    await detector.stop()  # should not raise

    assert detector._stream is None


# ---------------------------------------------------------------------------
# _blocking_audio_loop
# ---------------------------------------------------------------------------


def test_blocking_audio_loop_missing_sounddevice_logs_and_returns():
    detector = WakeWordDetector()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sounddevice":
            raise ImportError("No module named 'sounddevice'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        detector._blocking_audio_loop()  # should not raise


def _mock_sounddevice_module(captured_callbacks: list) -> MagicMock:
    mock_sd = MagicMock()

    def fake_input_stream(**kwargs):
        captured_callbacks.append(kwargs.get("callback"))
        stream = MagicMock()
        stream.__enter__ = MagicMock(return_value=stream)
        stream.__exit__ = MagicMock(return_value=False)
        return stream

    mock_sd.InputStream = fake_input_stream
    return mock_sd


def test_blocking_audio_loop_exits_immediately_when_not_running():
    detector = WakeWordDetector()
    detector._running = False  # loop body should never execute
    captured: list = []
    mock_sd = _mock_sounddevice_module(captured)

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        detector._blocking_audio_loop()

    assert len(captured) == 1  # InputStream was constructed
    assert detector._stream is not None


def test_blocking_audio_loop_handles_stream_construction_error():
    detector = WakeWordDetector()
    detector._running = False
    mock_sd = MagicMock()
    mock_sd.InputStream = MagicMock(side_effect=Exception("no audio device"))

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        detector._blocking_audio_loop()  # should not raise


def test_audio_callback_invokes_predict_and_check_scores():
    detector = WakeWordDetector()
    detector._running = False
    detector._oww = MagicMock()
    detector._oww.predict = MagicMock(return_value={"hey_jarvis": 0.1})
    captured: list = []
    mock_sd = _mock_sounddevice_module(captured)

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        detector._blocking_audio_loop()

    callback = captured[0]
    indata = np.zeros((1280, 1), dtype="int16")
    callback(indata, 1280, None, None)

    detector._oww.predict.assert_called_once()


def test_blocking_audio_loop_runs_until_running_flips_false():
    detector = WakeWordDetector()
    detector._running = True
    captured: list = []
    mock_sd = _mock_sounddevice_module(captured)

    def fake_sleep(seconds):
        detector._running = False  # stop after first iteration

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        with patch("time.sleep", side_effect=fake_sleep):
            detector._blocking_audio_loop()

    assert detector._running is False


def test_audio_callback_no_oww_skips_predict():
    detector = WakeWordDetector()
    detector._running = False
    detector._oww = None
    captured: list = []
    mock_sd = _mock_sounddevice_module(captured)

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        detector._blocking_audio_loop()

    callback = captured[0]
    indata = np.zeros((1280, 1), dtype="int16")
    callback(indata, 1280, None, MagicMock())  # status truthy branch too


# ---------------------------------------------------------------------------
# _check_scores
# ---------------------------------------------------------------------------


def test_check_scores_below_threshold_no_callback():
    fired = []
    detector = WakeWordDetector(threshold=0.5, on_wake=lambda: fired.append(1))
    detector._check_scores({"hey_jarvis": 0.1})
    assert fired == []


def test_check_scores_above_threshold_calls_sync_callback():
    fired = []
    detector = WakeWordDetector(threshold=0.5, on_wake=lambda: fired.append(1), cooldown=0.0)
    detector._check_scores({"hey_jarvis": 0.9})
    assert fired == [1]


def test_check_scores_respects_cooldown():
    fired = []
    detector = WakeWordDetector(threshold=0.5, on_wake=lambda: fired.append(1), cooldown=100.0)
    detector._last_detection = time.monotonic()
    detector._check_scores({"hey_jarvis": 0.9})
    assert fired == []


def test_check_scores_no_callback_set_does_not_raise():
    detector = WakeWordDetector(threshold=0.5, cooldown=0.0)
    detector._check_scores({"hey_jarvis": 0.9})  # no on_wake set


@pytest.mark.asyncio
async def test_check_scores_schedules_async_callback():
    async def async_callback():
        pass

    detector = WakeWordDetector(threshold=0.5, on_wake=async_callback, cooldown=0.0)

    with patch("asyncio.run_coroutine_threadsafe") as mock_schedule:
        detector._check_scores({"hey_jarvis": 0.9})

    mock_schedule.assert_called_once()
    # Close the coroutine object passed in to avoid an "never awaited" warning.
    mock_schedule.call_args[0][0].close()


def test_check_scores_swallows_runtime_error_for_coroutine_callback():
    async def async_callback():
        pass

    detector = WakeWordDetector(threshold=0.5, on_wake=async_callback, cooldown=0.0)

    with patch("asyncio.get_event_loop", side_effect=RuntimeError("no event loop")):
        detector._check_scores({"hey_jarvis": 0.9})  # should not raise; coroutine gets closed


def test_check_scores_fires_only_once_per_chunk():
    fired = []
    detector = WakeWordDetector(threshold=0.5, on_wake=lambda: fired.append(1), cooldown=0.0)
    detector._check_scores({"hey_jarvis": 0.9, "ok_nabu": 0.8})
    assert len(fired) == 1

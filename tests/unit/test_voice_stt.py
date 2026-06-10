"""Unit tests for cortexflow.voice.stt — WhisperSTT."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow.voice.stt import WhisperSTT


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_default_model_size():
    s = WhisperSTT()
    assert s.model_size == "base"


def test_default_device():
    s = WhisperSTT()
    assert s.device == "cpu"


def test_default_language_is_none():
    s = WhisperSTT()
    assert s.language is None


def test_custom_params():
    s = WhisperSTT(model_size="small", device="cuda", language="de")
    assert s.model_size == "small"
    assert s.device == "cuda"
    assert s.language == "de"


def test_model_not_loaded_on_init():
    s = WhisperSTT()
    assert s._model is None


# ---------------------------------------------------------------------------
# _load — missing faster_whisper raises RuntimeError
# ---------------------------------------------------------------------------


def test_load_raises_if_faster_whisper_not_installed():
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("No module named 'faster_whisper'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        s = WhisperSTT()
        with pytest.raises(RuntimeError, match="pip install faster-whisper"):
            s._load()


# ---------------------------------------------------------------------------
# _load — model is cached after first call
# ---------------------------------------------------------------------------


def test_load_caches_model():
    mock_model = MagicMock()

    mock_whisper_module = MagicMock()
    mock_whisper_module.WhisperModel = MagicMock(return_value=mock_model)

    with patch.dict("sys.modules", {"faster_whisper": mock_whisper_module}):
        s = WhisperSTT()
        m1 = s._load()
        m2 = s._load()

    assert m1 is m2
    mock_whisper_module.WhisperModel.assert_called_once()


# ---------------------------------------------------------------------------
# _run — joins segments
# ---------------------------------------------------------------------------


def test_run_joins_segments():
    seg1 = MagicMock()
    seg1.text = " Hello"
    seg2 = MagicMock()
    seg2.text = " world."

    mock_model = MagicMock()
    mock_model.transcribe = MagicMock(return_value=([seg1, seg2], MagicMock()))

    s = WhisperSTT()
    result = s._run(mock_model, Path("dummy.ogg"))
    assert result == "Hello world."


def test_run_empty_segments_returns_empty():
    mock_model = MagicMock()
    mock_model.transcribe = MagicMock(return_value=([], MagicMock()))

    s = WhisperSTT()
    result = s._run(mock_model, Path("dummy.ogg"))
    assert result == ""


# ---------------------------------------------------------------------------
# transcribe — delegates to executor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_returns_string():
    s = WhisperSTT()
    s._transcribe_sync = MagicMock(return_value="hello world")
    result = await s.transcribe(b"fake audio bytes")
    assert result == "hello world"


@pytest.mark.asyncio
async def test_transcribe_path_input():
    s = WhisperSTT()
    s._transcribe_sync = MagicMock(return_value="from file")
    result = await s.transcribe(Path("audio.ogg"))
    assert result == "from file"


# ---------------------------------------------------------------------------
# transcribe_stream — yields partial results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_stream_yields_text():
    s = WhisperSTT()
    s._transcribe_sync = MagicMock(return_value="chunk transcript")

    async def fake_chunks():
        chunk = b"X" * 40_000  # larger than buffer_size
        yield chunk

    results = []
    async for text in s.transcribe_stream(fake_chunks()):
        results.append(text)

    assert len(results) >= 1
    assert results[0] == "chunk transcript"


@pytest.mark.asyncio
async def test_transcribe_stream_skips_empty_transcripts():
    s = WhisperSTT()
    s._transcribe_sync = MagicMock(return_value="")

    async def fake_chunks():
        yield b"X" * 40_000

    results = []
    async for text in s.transcribe_stream(fake_chunks()):
        results.append(text)

    assert results == []

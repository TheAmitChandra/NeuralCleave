"""Tests for WhisperSTT._transcribe_sync numpy fast-path vs fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from neuralcleave.voice.stt import WhisperSTT


def _make_stt() -> WhisperSTT:
    s = WhisperSTT.__new__(WhisperSTT)
    s._model = None
    s.model_size = "tiny"
    s.language = "en"
    s.device = "cpu"
    return s


def _make_model(segments: list[str]) -> MagicMock:
    model = MagicMock()
    seg_objs = [MagicMock(text=t) for t in segments]
    model.transcribe.return_value = (iter(seg_objs), MagicMock())
    return model


class TestNumpyFastPath:
    def test_numpy_path_returns_joined_text(self) -> None:
        """normalise_to_pcm succeeds → Whisper called with numpy array."""
        stt = _make_stt()
        model = _make_model(["hello", "world"])
        pcm = np.zeros(16000, dtype=np.float32)

        with patch.object(stt, "_load", return_value=model):
            with patch(
                "neuralcleave.voice.audio.normalise_to_pcm", return_value=pcm
            ) as mock_norm:
                result = stt._transcribe_sync(b"audio_bytes")

        assert result == "hello world"
        mock_norm.assert_called_once_with(b"audio_bytes", target_sr=16_000)
        args, _ = model.transcribe.call_args
        assert isinstance(args[0], np.ndarray)

    def test_numpy_path_uses_16khz_sampling_rate(self) -> None:
        """Whisper call includes sampling_rate=16000."""
        stt = _make_stt()
        model = _make_model(["hi"])
        pcm = np.zeros(100, dtype=np.float32)

        with patch.object(stt, "_load", return_value=model):
            with patch("neuralcleave.voice.audio.normalise_to_pcm", return_value=pcm):
                stt._transcribe_sync(b"audio")

        _, kwargs = model.transcribe.call_args
        assert kwargs.get("sampling_rate") == 16_000

    def test_numpy_path_strips_whitespace(self) -> None:
        """Leading/trailing spaces in segment texts are stripped."""
        stt = _make_stt()
        model = _make_model(["  hi  ", " there "])
        pcm = np.zeros(100, dtype=np.float32)

        with patch.object(stt, "_load", return_value=model):
            with patch("neuralcleave.voice.audio.normalise_to_pcm", return_value=pcm):
                result = stt._transcribe_sync(b"audio")

        assert result == "hi there"

    def test_numpy_path_uses_language(self) -> None:
        """Whisper call forwards the configured language."""
        stt = _make_stt()
        stt.language = "fr"
        model = _make_model(["bonjour"])
        pcm = np.zeros(100, dtype=np.float32)

        with patch.object(stt, "_load", return_value=model):
            with patch("neuralcleave.voice.audio.normalise_to_pcm", return_value=pcm):
                stt._transcribe_sync(b"audio")

        _, kwargs = model.transcribe.call_args
        assert kwargs.get("language") == "fr"


class TestFallbackTempFilePath:
    def test_fallback_used_when_normalise_raises(self, tmp_path: Path) -> None:
        """normalise_to_pcm raises → falls through to temp-file path."""
        stt = _make_stt()
        model = _make_model(["fallback text"])

        def run_side_effect(model_obj, path):
            assert isinstance(path, Path)
            return "fallback text"

        with patch.object(stt, "_load", return_value=model):
            with patch(
                "neuralcleave.voice.audio.normalise_to_pcm",
                side_effect=ImportError("soundfile missing"),
            ):
                with patch.object(stt, "_run", side_effect=run_side_effect) as mock_run:
                    result = stt._transcribe_sync(b"raw audio bytes")

        assert result == "fallback text"
        mock_run.assert_called_once()

    def test_fallback_cleans_up_temp_file(self, tmp_path: Path) -> None:
        """Temp file is deleted even if _run raises."""
        stt = _make_stt()
        model = MagicMock()

        created: list[str] = []

        def recording_run(model_obj, path):
            created.append(str(path))
            raise RuntimeError("transcription failed")

        with patch.object(stt, "_load", return_value=model):
            with patch(
                "neuralcleave.voice.audio.normalise_to_pcm",
                side_effect=ImportError("no soundfile"),
            ):
                with patch.object(stt, "_run", side_effect=recording_run):
                    with pytest.raises(RuntimeError):
                        stt._transcribe_sync(b"audio")

        for p in created:
            assert not Path(p).exists()

    def test_path_input_skips_numpy_entirely(self) -> None:
        """Path input always goes to _run, never normalise_to_pcm."""
        stt = _make_stt()
        model = _make_model(["path transcript"])

        with patch.object(stt, "_load", return_value=model):
            with patch("neuralcleave.voice.audio.normalise_to_pcm") as mock_norm:
                with patch.object(stt, "_run", return_value="path transcript"):
                    result = stt._transcribe_sync(Path("/fake/file.ogg"))

        mock_norm.assert_not_called()
        assert result == "path transcript"

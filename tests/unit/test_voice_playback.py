"""Tests for neuralcleave.voice.audio.play_audio."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from neuralcleave.voice.audio import play_audio


class TestPlayAudio:
    def test_play_audio_calls_sounddevice_play(self) -> None:
        mock_sd = MagicMock()
        mock_sf = MagicMock()
        mock_sf.read.return_value = (MagicMock(), 22050)

        with patch.dict("sys.modules", {"sounddevice": mock_sd, "soundfile": mock_sf}):
            play_audio(b"\x00\x01" * 100)

        mock_sd.play.assert_called_once()
        mock_sd.wait.assert_called_once()

    def test_play_audio_passes_sample_rate_to_sounddevice(self) -> None:
        import numpy as np

        mock_sd = MagicMock()
        mock_sf = MagicMock()
        fake_data = np.zeros(100, dtype="float32")
        mock_sf.read.return_value = (fake_data, 24000)

        with patch.dict("sys.modules", {"sounddevice": mock_sd, "soundfile": mock_sf}):
            play_audio(b"\x00" * 200)

        _, kwargs = mock_sd.play.call_args
        assert kwargs.get("samplerate") == 24000

    def test_play_audio_reads_bytes_as_io_bytesio(self) -> None:
        mock_sd = MagicMock()
        mock_sf = MagicMock()
        mock_sf.read.return_value = (MagicMock(), 16000)
        captured: list[bytes] = []

        def fake_read(buf, dtype):
            captured.append(buf.read())
            return mock_sf.read.return_value

        mock_sf.read.side_effect = fake_read
        audio = b"\x01\x02\x03"

        with patch.dict("sys.modules", {"sounddevice": mock_sd, "soundfile": mock_sf}):
            play_audio(audio)

        assert captured[0] == audio

    def test_play_audio_swallows_sounddevice_error(self) -> None:
        mock_sd = MagicMock()
        mock_sf = MagicMock()
        mock_sf.read.return_value = (MagicMock(), 22050)
        mock_sd.play.side_effect = RuntimeError("no audio device")

        with patch.dict("sys.modules", {"sounddevice": mock_sd, "soundfile": mock_sf}):
            play_audio(b"\x00" * 100)  # must not raise

    def test_play_audio_swallows_soundfile_error(self) -> None:
        mock_sd = MagicMock()
        mock_sf = MagicMock()
        mock_sf.read.side_effect = RuntimeError("unrecognised format")

        with patch.dict("sys.modules", {"sounddevice": mock_sd, "soundfile": mock_sf}):
            play_audio(b"\x00" * 100)  # must not raise

    def test_play_audio_missing_sounddevice_swallowed(self) -> None:
        with patch.dict("sys.modules", {"sounddevice": None, "soundfile": None}):
            play_audio(b"\x00" * 100)  # must not raise

    def test_play_audio_exported_from_voice_package(self) -> None:
        from neuralcleave.voice import play_audio as exported
        assert exported is play_audio

"""Tests for the device parameter in play_audio()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestPlayAudioDevice:
    def _make_sd_sf(self) -> tuple[MagicMock, MagicMock]:
        import numpy as np
        sf = MagicMock()
        sf.read.return_value = (np.zeros(16000, dtype="float32"), 16000)
        sd = MagicMock()
        return sd, sf

    def test_device_none_passed_to_sd_play(self) -> None:
        from neuralcleave.voice.audio import play_audio

        sd, sf = self._make_sd_sf()
        with patch.dict("sys.modules", {"sounddevice": sd, "soundfile": sf}):
            play_audio(b"\x00" * 100, device=None)
        sd.play.assert_called_once()
        _, kwargs = sd.play.call_args
        assert kwargs.get("device") is None

    def test_device_index_forwarded(self) -> None:
        from neuralcleave.voice.audio import play_audio

        sd, sf = self._make_sd_sf()
        with patch.dict("sys.modules", {"sounddevice": sd, "soundfile": sf}):
            play_audio(b"\x00" * 100, device=2)
        _, kwargs = sd.play.call_args
        assert kwargs.get("device") == 2

    def test_device_string_forwarded(self) -> None:
        from neuralcleave.voice.audio import play_audio

        sd, sf = self._make_sd_sf()
        with patch.dict("sys.modules", {"sounddevice": sd, "soundfile": sf}):
            play_audio(b"\x00" * 100, device="USB Speaker")
        _, kwargs = sd.play.call_args
        assert kwargs.get("device") == "USB Speaker"

    def test_default_signature_unchanged(self) -> None:
        """Calling play_audio without device should still work (no regression)."""
        from neuralcleave.voice.audio import play_audio

        sd, sf = self._make_sd_sf()
        with patch.dict("sys.modules", {"sounddevice": sd, "soundfile": sf}):
            play_audio(b"\x00" * 100)
        sd.play.assert_called_once()

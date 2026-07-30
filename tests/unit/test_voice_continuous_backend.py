"""Tests for vad_backend parameter on ContinuousVoiceListener."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from neuralcleave.voice.continuous import ContinuousVoiceListener
from neuralcleave.voice.vad import VoiceActivityDetector

_FAKE_WEBRTCVAD = MagicMock()
_FAKE_WEBRTCVAD.Vad.return_value = MagicMock()


class TestContinuousListenerVadBackend:
    def test_default_vad_backend_is_energy(self) -> None:
        stt = MagicMock()
        listener = ContinuousVoiceListener(stt)
        assert listener._vad.backend == "energy"

    def test_custom_vad_backend_forwarded_to_vad(self) -> None:
        stt = MagicMock()
        with patch.dict("sys.modules", {"webrtcvad": _FAKE_WEBRTCVAD}):
            listener = ContinuousVoiceListener(stt, vad_backend="webrtcvad")
        assert listener._vad.backend == "webrtcvad"

    def test_energy_backend_explicit(self) -> None:
        stt = MagicMock()
        listener = ContinuousVoiceListener(stt, vad_backend="energy")
        assert listener._vad.backend == "energy"

    def test_vad_object_is_voice_activity_detector(self) -> None:
        stt = MagicMock()
        listener = ContinuousVoiceListener(stt)
        assert isinstance(listener._vad, VoiceActivityDetector)

    def test_vad_backend_and_aggressiveness_together(self) -> None:
        stt = MagicMock()
        with patch.dict("sys.modules", {"webrtcvad": _FAKE_WEBRTCVAD}):
            listener = ContinuousVoiceListener(stt, vad_backend="webrtcvad", vad_aggressiveness=3)
        assert listener._vad.backend == "webrtcvad"
        assert listener._vad.aggressiveness == 3

    def test_vad_exposed_via_property(self) -> None:
        stt = MagicMock()
        listener = ContinuousVoiceListener(stt, vad_backend="energy")
        assert listener.vad is listener._vad


class TestVoiceActivityDetectorBackend:
    def test_energy_backend_stored(self) -> None:
        vad = VoiceActivityDetector(backend="energy")
        assert vad.backend == "energy"

    def test_webrtcvad_backend_stored(self) -> None:
        with patch.dict("sys.modules", {"webrtcvad": _FAKE_WEBRTCVAD}):
            vad = VoiceActivityDetector(backend="webrtcvad")
        assert vad.backend == "webrtcvad"

    def test_default_backend_is_energy(self) -> None:
        vad = VoiceActivityDetector()
        assert vad.backend == "energy"

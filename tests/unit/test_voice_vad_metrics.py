"""Tests for VAD metric counters in the observability registry."""

from __future__ import annotations

from neuralcleave.observability.metrics import REGISTRY


class TestVADMetricsRegistered:
    def test_speech_frames_counter_registered(self) -> None:
        assert REGISTRY.get("vad_speech_frames_total") is not None

    def test_silence_frames_counter_registered(self) -> None:
        assert REGISTRY.get("vad_silence_frames_total") is not None

    def test_utterances_counter_registered(self) -> None:
        assert REGISTRY.get("vad_utterances_total") is not None


class TestVADMetricsIncrement:
    def test_speech_frames_increments(self) -> None:
        before = REGISTRY.get("vad_speech_frames_total").get()
        REGISTRY.inc("vad_speech_frames_total", 5.0)
        after = REGISTRY.get("vad_speech_frames_total").get()
        assert after == before + 5.0

    def test_silence_frames_increments(self) -> None:
        before = REGISTRY.get("vad_silence_frames_total").get()
        REGISTRY.inc("vad_silence_frames_total", 3.0)
        after = REGISTRY.get("vad_silence_frames_total").get()
        assert after == before + 3.0

    def test_utterances_increments(self) -> None:
        before = REGISTRY.get("vad_utterances_total").get()
        REGISTRY.inc("vad_utterances_total")
        after = REGISTRY.get("vad_utterances_total").get()
        assert after == before + 1.0


class TestVADMetricsPrometheus:
    def test_prometheus_export_includes_vad_counters(self) -> None:
        output = REGISTRY.export_prometheus()
        assert "vad_speech_frames_total" in output
        assert "vad_silence_frames_total" in output
        assert "vad_utterances_total" in output

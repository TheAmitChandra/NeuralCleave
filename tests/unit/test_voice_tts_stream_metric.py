"""Tests that voice_tts_stream_chunks_total metric is registered."""

from __future__ import annotations


class TestVoiceTtsStreamMetric:
    def test_metric_registered(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        snap = REGISTRY.snapshot()
        assert "voice_tts_stream_chunks_total" in snap

    def test_metric_starts_at_zero_or_is_counter(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        snap = REGISTRY.snapshot()
        metric = snap["voice_tts_stream_chunks_total"]
        assert metric["type"] == "counter"

    def test_metric_increments(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        before = REGISTRY.snapshot()["voice_tts_stream_chunks_total"]["values"].get("", 0.0)
        REGISTRY.inc("voice_tts_stream_chunks_total")
        after = REGISTRY.snapshot()["voice_tts_stream_chunks_total"]["values"].get("", 0.0)
        assert after == before + 1.0

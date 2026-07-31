"""Tests for voice_sessions_total and voice_session_turns_total metrics."""

from __future__ import annotations

from neuralcleave.observability.metrics import REGISTRY, Counter


class TestVoiceSessionMetrics:
    def test_voice_sessions_total_registered(self) -> None:
        import neuralcleave.observability.metrics  # noqa: F401

        assert REGISTRY.get("voice_sessions_total") is not None

    def test_voice_session_turns_total_registered(self) -> None:
        import neuralcleave.observability.metrics  # noqa: F401

        assert REGISTRY.get("voice_session_turns_total") is not None

    def test_voice_sessions_total_is_counter(self) -> None:
        assert isinstance(REGISTRY.get("voice_sessions_total"), Counter)

    def test_voice_session_turns_total_is_counter(self) -> None:
        assert isinstance(REGISTRY.get("voice_session_turns_total"), Counter)

    def test_voice_sessions_total_increments(self) -> None:
        metric = REGISTRY.get("voice_sessions_total")
        before = metric.get()
        REGISTRY.inc("voice_sessions_total")
        assert metric.get() == before + 1.0

    def test_voice_session_turns_total_increments(self) -> None:
        metric = REGISTRY.get("voice_session_turns_total")
        before = metric.get()
        REGISTRY.inc("voice_session_turns_total")
        assert metric.get() == before + 1.0

    def test_voice_sessions_total_description_nonempty(self) -> None:
        assert len(REGISTRY.get("voice_sessions_total").description) > 0

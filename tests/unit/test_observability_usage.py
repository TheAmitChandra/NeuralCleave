"""Tests for neuralcleave.observability.usage — per-model usage summary (P2, 2026-08-17 gap analysis)."""

from __future__ import annotations

from neuralcleave.observability.metrics import REGISTRY
from neuralcleave.observability.usage import usage_summary


def _reset(model: str, provider: str) -> None:
    REGISTRY.get("tokens_total").reset(labels={"model": model, "direction": "input"})
    REGISTRY.get("tokens_total").reset(labels={"model": model, "direction": "output"})
    REGISTRY.get("cost_usd_total").reset(labels={"model": model, "provider": provider})


class TestUsageSummary:
    def test_empty_registry_state_returns_zeros_not_missing_model(self) -> None:
        _reset("usage-test-empty-model", "google")
        summary = usage_summary()
        assert summary.get("usage-test-empty-model") in (None, {"input_tokens": 0.0, "output_tokens": 0.0, "cost_usd": 0.0})

    def test_aggregates_tokens_and_cost_for_one_model(self) -> None:
        model, provider = "usage-test-model-a", "anthropic"
        _reset(model, provider)

        REGISTRY.inc("tokens_total", 100, labels={"model": model, "direction": "input"})
        REGISTRY.inc("tokens_total", 40, labels={"model": model, "direction": "output"})
        REGISTRY.inc("cost_usd_total", 0.0057, labels={"model": model, "provider": provider})

        summary = usage_summary()

        assert summary[model]["input_tokens"] == 100
        assert summary[model]["output_tokens"] == 40
        assert summary[model]["cost_usd"] == 0.0057

    def test_two_models_stay_independent(self) -> None:
        _reset("usage-test-model-b1", "openai")
        _reset("usage-test-model-b2", "openai")

        REGISTRY.inc("tokens_total", 10, labels={"model": "usage-test-model-b1", "direction": "input"})
        REGISTRY.inc("tokens_total", 20, labels={"model": "usage-test-model-b2", "direction": "input"})

        summary = usage_summary()

        assert summary["usage-test-model-b1"]["input_tokens"] == 10
        assert summary["usage-test-model-b2"]["input_tokens"] == 20

    def test_tokens_without_matching_cost_entry_still_reports_zero_cost(self) -> None:
        model = "usage-test-model-unpriced"
        _reset(model, "openrouter")

        REGISTRY.inc("tokens_total", 500, labels={"model": model, "direction": "input"})
        # No cost_usd_total entry recorded — mirrors an unpriced provider.

        summary = usage_summary()

        assert summary[model]["input_tokens"] == 500
        assert summary[model]["cost_usd"] == 0.0

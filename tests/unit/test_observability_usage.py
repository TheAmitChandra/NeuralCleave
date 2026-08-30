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
        entry = summary.get("usage-test-empty-model")
        assert entry is None or entry == {
            "input_tokens": 0.0, "output_tokens": 0.0, "cost_usd": 0.0, "unpriced": False
        }

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


class TestUsageSummaryDistinguishesUnpricedFromFree:
    """Round 8 gap analysis 5.1b (2026-08-30): pricing.py deliberately
    returns None (not 0.0) so callers can tell "unknown; don't report a
    misleading number" apart from "genuinely free" - but usage_summary()
    used to initialise cost_usd: 0.0 for every model with any token
    counter, discarding that distinction and rendering both cases
    identically as $0.0000. cost_unpriced_generations_total is what
    restores it."""

    def test_a_model_marked_unpriced_reports_cost_as_none(self) -> None:
        model = "usage-test-genuinely-unpriced"
        REGISTRY.get("tokens_total").reset(labels={"model": model, "direction": "input"})
        REGISTRY.get("tokens_total").reset(labels={"model": model, "direction": "output"})
        REGISTRY.get("cost_usd_total").reset(labels={"model": model, "provider": "openrouter"})
        REGISTRY.get("cost_unpriced_generations_total").reset(labels={"model": model, "provider": "openrouter"})

        REGISTRY.inc("tokens_total", 500, labels={"model": model, "direction": "input"})
        REGISTRY.inc("cost_unpriced_generations_total", labels={"model": model, "provider": "openrouter"})

        summary = usage_summary()

        assert summary[model]["cost_usd"] is None
        assert summary[model]["unpriced"] is True
        assert summary[model]["input_tokens"] == 500

    def test_a_genuinely_free_model_reports_cost_as_zero_not_none(self) -> None:
        """Ollama (provider="ollama") is a real, deliberate $0.0 - never
        marked unpriced, so it must stay distinguishable from the case
        above."""
        model = "usage-test-genuinely-free"
        REGISTRY.get("tokens_total").reset(labels={"model": model, "direction": "input"})
        REGISTRY.get("cost_usd_total").reset(labels={"model": model, "provider": "ollama"})

        REGISTRY.inc("tokens_total", 500, labels={"model": model, "direction": "input"})
        REGISTRY.inc("cost_usd_total", 0.0, labels={"model": model, "provider": "ollama"})

        summary = usage_summary()

        assert summary[model]["cost_usd"] == 0.0
        assert summary[model]["unpriced"] is False

"""Tests for neuralcleave.models.thinking — normalized reasoning-effort
mapping (P7, 2026-08-17 gap analysis).
"""

from __future__ import annotations

import pytest

from neuralcleave.models.thinking import THINKING_LEVELS, resolve_thinking_params


class TestThinkingLevels:
    def test_six_levels_in_expected_order(self):
        assert THINKING_LEVELS == ("off", "low", "medium", "high", "xhigh", "max")


class TestAnthropic:
    def test_off_disables_extended_thinking(self):
        params = resolve_thinking_params("anthropic", "off")
        assert params["extended_thinking"] is False

    @pytest.mark.parametrize(
        "level,expected_budget",
        [("low", 2048), ("medium", 4096), ("high", 8192), ("xhigh", 16384), ("max", 32000)],
    )
    def test_each_level_enables_thinking_with_scaled_budget(self, level, expected_budget):
        params = resolve_thinking_params("anthropic", level)
        assert params["extended_thinking"] is True
        assert params["thinking_budget_tokens"] == expected_budget

    def test_budgets_strictly_increase_with_level(self):
        budgets = [
            resolve_thinking_params("anthropic", level)["thinking_budget_tokens"]
            for level in ("low", "medium", "high", "xhigh", "max")
        ]
        assert budgets == sorted(budgets)
        assert len(set(budgets)) == len(budgets)


class TestOpenAIStyleReasoningProviders:
    @pytest.mark.parametrize("provider", ["xai", "openrouter"])
    def test_off_returns_empty_dict(self, provider):
        assert resolve_thinking_params(provider, "off") == {}

    @pytest.mark.parametrize("provider", ["xai", "openrouter"])
    @pytest.mark.parametrize("level,expected", [("low", "low"), ("medium", "medium"), ("high", "high")])
    def test_direct_tiers_map_one_to_one(self, provider, level, expected):
        assert resolve_thinking_params(provider, level) == {"reasoning_effort": expected}

    @pytest.mark.parametrize("provider", ["xai", "openrouter"])
    @pytest.mark.parametrize("level", ["xhigh", "max"])
    def test_levels_above_high_collapse_to_high(self, provider, level):
        assert resolve_thinking_params(provider, level) == {"reasoning_effort": "high"}


class TestOllama:
    """Ollama collapses the 6-level ladder to a boolean `think` field — some
    models accept a 3-tier string but many reasoning models only accept a
    boolean, and NeuralCleave has no way to know which kind was pulled."""

    def test_off_maps_to_false(self):
        assert resolve_thinking_params("ollama", "off") == {"think": False}

    @pytest.mark.parametrize("level", ["low", "medium", "high", "xhigh", "max"])
    def test_every_other_level_maps_to_true(self, level):
        assert resolve_thinking_params("ollama", level) == {"think": True}


class TestUnsupportedProviders:
    @pytest.mark.parametrize("provider", ["cohere", "google", "deepseek", "not-a-real-provider"])
    @pytest.mark.parametrize("level", ["off", "low", "medium", "high", "xhigh", "max"])
    def test_returns_empty_dict_for_every_level(self, provider, level):
        assert resolve_thinking_params(provider, level) == {}

    def test_deepseek_has_no_per_request_lever_by_design(self):
        """DeepSeek's API has no reasoning-effort field at all — the only
        real lever is which model you call (deepseek-chat vs.
        deepseek-reasoner), an explicit user config choice. Faking a
        parameter their API doesn't accept would be its own "looks wired
        but does nothing" bug."""
        for level in ("off", "low", "medium", "high", "xhigh", "max"):
            assert resolve_thinking_params("deepseek", level) == {}


class TestInvalidLevel:
    def test_unknown_level_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown thinking level"):
            resolve_thinking_params("anthropic", "ultra-max-plus")

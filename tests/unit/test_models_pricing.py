"""Tests for neuralcleave.models.pricing — cost estimation (P2, gap analysis 2026-08-17)."""

from __future__ import annotations

from neuralcleave.models.pricing import estimate_cost_usd


class TestKnownModelPricing:
    def test_anthropic_exact_family_match(self) -> None:
        cost = estimate_cost_usd(
            provider="anthropic", model="claude-opus", input_tokens=1_000_000, output_tokens=0
        )
        assert cost == 15.0

    def test_anthropic_versioned_model_matches_by_prefix(self) -> None:
        cost = estimate_cost_usd(
            provider="anthropic", model="claude-opus-4-8", input_tokens=1_000_000, output_tokens=0
        )
        assert cost == 15.0

    def test_output_tokens_priced_separately_from_input(self) -> None:
        cost = estimate_cost_usd(
            provider="anthropic", model="claude-sonnet-4", input_tokens=0, output_tokens=1_000_000
        )
        assert cost == 15.0

    def test_combined_input_and_output_cost(self) -> None:
        cost = estimate_cost_usd(
            provider="openai", model="gpt-4o", input_tokens=1_000_000, output_tokens=1_000_000
        )
        assert cost == 2.5 + 10.0

    def test_zero_tokens_costs_nothing(self) -> None:
        cost = estimate_cost_usd(provider="openai", model="gpt-4o", input_tokens=0, output_tokens=0)
        assert cost == 0.0

    def test_fractional_token_counts_scale_linearly(self) -> None:
        cost = estimate_cost_usd(
            provider="deepseek", model="deepseek-chat", input_tokens=500_000, output_tokens=0
        )
        assert cost == 0.135


class TestLongestPrefixWins:
    def test_gpt_4o_mini_does_not_match_plain_gpt_4o_pricing(self) -> None:
        mini_cost = estimate_cost_usd(
            provider="openai", model="gpt-4o-mini", input_tokens=1_000_000, output_tokens=0
        )
        full_cost = estimate_cost_usd(
            provider="openai", model="gpt-4o", input_tokens=1_000_000, output_tokens=0
        )
        assert mini_cost == 0.15
        assert full_cost == 2.5
        assert mini_cost != full_cost

    def test_dated_gpt_4o_mini_variant_matches_mini_not_full(self) -> None:
        cost = estimate_cost_usd(
            provider="openai", model="gpt-4o-mini-2024-07-18", input_tokens=1_000_000, output_tokens=0
        )
        assert cost == 0.15


class TestOllamaAlwaysFree:
    def test_ollama_returns_zero_regardless_of_model(self) -> None:
        cost = estimate_cost_usd(
            provider="ollama", model="llama3.2:1b", input_tokens=1_000_000, output_tokens=1_000_000
        )
        assert cost == 0.0


class TestUnknownPricingReturnsNone:
    def test_unpriced_provider_returns_none(self) -> None:
        cost = estimate_cost_usd(
            provider="openrouter", model="anything/whatever", input_tokens=1000, output_tokens=1000
        )
        assert cost is None

    def test_unpriced_model_within_known_provider_returns_none(self) -> None:
        cost = estimate_cost_usd(
            provider="anthropic", model="totally-unknown-model", input_tokens=1000, output_tokens=1000
        )
        assert cost is None

    def test_unknown_provider_returns_none(self) -> None:
        cost = estimate_cost_usd(
            provider="not-a-real-provider", model="x", input_tokens=1000, output_tokens=1000
        )
        assert cost is None

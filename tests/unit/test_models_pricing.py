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


class TestEveryRoutedModelIsPricedOrExplicitlyUnpriceable:
    """Round 8 gap analysis 5.1b (2026-08-30): pricing.py was written on
    2026-08-17 carrying gemini-1.5-pro/gemini-2.0-flash entries the router
    had already replaced on 2026-07-20 - it was stale from the moment it
    was written, and nothing caught it because no test cross-checked the
    two tables against each other. This test is that cross-check: every
    model _ROUTING can actually select must either have a real pricing.py
    entry, or be explicitly named below as a deliberate omission (a
    contract/underlying-model-dependent aggregator whose price genuinely
    can't be guessed). A new routed model that's neither is a bug this
    test catches on the day it's introduced, not a month later.
    """

    # provider/model pairs whose price genuinely cannot be responsibly
    # guessed - contract or underlying-model-dependent pricing. Anything
    # NOT on this list is expected to have a real pricing.py entry.
    _DELIBERATELY_UNPRICEABLE = {
        ("openrouter", "openai/gpt-4o-mini"),
        ("azure", "gpt-4o"),
        ("bedrock", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
    }

    # (provider, routed model constant, routing-namespace prefix to strip
    # before pricing lookup - matching ModelRouter._call()'s own dispatch,
    # since that's what actually reaches GenerationResult.model).
    _ROUTED_MODELS = [
        ("anthropic", "claude-opus-4-8", None),
        ("anthropic", "claude-sonnet-4-6", None),
        ("google", "gemini-2.5-pro", None),
        ("google", "gemini-2.5-flash", None),
        ("deepseek", "deepseek-coder", None),
        ("ollama", "ollama/llama3.2:1b", None),
        ("openai", "gpt-4o", None),
        ("openai", "gpt-4o-mini", None),
        ("mistral", "mistral-large-latest", None),
        ("mistral", "mistral-small-latest", None),
        ("xai", "grok-3", None),
        ("xai", "grok-3-mini", None),
        ("cohere", "command-r-plus", None),
        ("cohere", "command-r", None),
        ("moonshot", "moonshot-v1-8k", None),
        ("zhipu", "glm-4", None),
        ("zhipu", "glm-4-flash", None),
        ("qwen", "qwen-max", None),
        ("qwen", "qwen-turbo", None),
        ("ernie", "ernie-bot-4", None),
        ("ernie", "ernie-speed", None),
        ("doubao", "doubao-pro-32k", None),
        ("doubao", "doubao-lite-32k", None),
        ("openrouter", "openrouter/openai/gpt-4o-mini", "openrouter/"),
        ("azure", "azure/gpt-4o", "azure/"),
        ("bedrock", "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", "bedrock/"),
        ("groq", "groq/llama-3.3-70b-versatile", "groq/"),
        ("together", "together/meta-llama/Llama-3.3-70B-Instruct-Turbo", "together/"),
        ("fireworks", "fireworks/accounts/fireworks/models/llama-v3p1-70b-instruct", "fireworks/"),
    ]

    def test_every_routed_model_prices_or_is_explicitly_unpriceable(self) -> None:
        unexpectedly_unpriced = []
        for provider, model_constant, strip_prefix in self._ROUTED_MODELS:
            model = model_constant[len(strip_prefix):] if strip_prefix else model_constant
            cost = estimate_cost_usd(provider=provider, model=model, input_tokens=1000, output_tokens=1000)
            if cost is None and (provider, model) not in self._DELIBERATELY_UNPRICEABLE:
                unexpectedly_unpriced.append((provider, model))
        assert unexpectedly_unpriced == [], (
            f"These provider/model pairs have no pricing.py entry and aren't on "
            f"_DELIBERATELY_UNPRICEABLE: {unexpectedly_unpriced}"
        )


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

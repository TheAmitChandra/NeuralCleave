"""Static per-model pricing table and USD cost estimation.

Token counts were already recorded (``tokens_total`` in
``neuralcleave/observability/metrics.py``) before this module existed; this
adds the missing piece — turning a token count into an approximate dollar
cost (P2 of the 2026-08-17 gap analysis).

Prices are USD per 1,000,000 tokens, input and output priced separately (the
usual provider convention). This is a maintained snapshot, not a live
lookup — provider pricing changes over time and this table will drift; treat
estimates as approximate, not a billing-grade source of truth.

Usage::

    from neuralcleave.models.pricing import estimate_cost_usd

    cost = estimate_cost_usd(
        provider="anthropic", model="claude-opus-4-8",
        input_tokens=1200, output_tokens=340,
    )
"""

from __future__ import annotations

# provider -> { model-name-prefix: (input_$_per_1M, output_$_per_1M) }
# Prefix matching handles versioned/dated model names (e.g. a user-configured
# "gpt-4o-2024-08-06" still matches the "gpt-4o" entry). Providers with no
# entry here (openrouter, azure, bedrock) have contract/underlying-model
# dependent pricing that can't be responsibly guessed — callers get None.
PRICING_PER_1M_TOKENS: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {
        "claude-opus": (15.0, 75.0),
        "claude-sonnet": (3.0, 15.0),
        "claude-haiku": (0.8, 4.0),
    },
    "openai": {
        "gpt-4o-mini": (0.15, 0.6),
        "gpt-4o": (2.5, 10.0),
        "gpt-3.5": (0.5, 1.5),
        "o1-mini": (1.1, 4.4),
        "o1": (15.0, 60.0),
    },
    "google": {
        # gemini-1.5-* / gemini-2.0-flash: retired router defaults (see
        # models/router.py's GEMINI_PRO/GEMINI_FLASH comment - both lost
        # their free-tier quota, replaced 2026-07-20 by the 2.5 generation
        # below). Kept in case a user manually configures one of these
        # older names via a forced-provider override.
        "gemini-1.5-flash": (0.075, 0.3),
        "gemini-1.5-pro": (1.25, 5.0),
        "gemini-2.0-flash": (0.1, 0.4),
        "gemini-2.5-flash": (0.30, 2.50),
        "gemini-2.5-pro": (1.25, 10.0),
    },
    "deepseek": {
        "deepseek-reasoner": (0.55, 2.19),
        "deepseek-chat": (0.27, 1.10),
        "deepseek-coder": (0.14, 0.28),
    },
    "mistral": {
        "mistral-large": (2.0, 6.0),
        "mistral-small": (0.2, 0.6),
    },
    "xai": {
        # grok-2 / grok-beta: retired router defaults, kept for the same
        # reason as the gemini-1.5-* entries above.
        "grok-2": (2.0, 10.0),
        "grok-beta": (5.0, 15.0),
        "grok-3-mini": (0.3, 0.5),
        "grok-3": (3.0, 15.0),
    },
    "cohere": {
        "command-r-plus": (2.5, 10.0),
        "command-r": (0.15, 0.6),
    },
    "moonshot": {
        "moonshot-v1": (0.2, 0.2),
    },
    "zhipu": {
        "glm-4": (0.1, 0.1),
    },
    "qwen": {
        "qwen-max": (1.6, 6.4),
        "qwen-plus": (0.4, 1.2),
        "qwen-turbo": (0.05, 0.2),
    },
    "ernie": {
        # ernie-4.0: retired router default name, kept for the same reason
        # as the gemini-1.5-* entries above (router now uses ernie-bot-4 /
        # ernie-speed - neither matched this entry's prefix at all).
        "ernie-4.0": (0.9, 1.8),
        "ernie-bot-4": (0.9, 1.8),
        "ernie-speed": (0.15, 0.3),
    },
    "doubao": {
        "doubao-pro": (0.11, 0.3),
        "doubao-lite": (0.02, 0.06),
    },
    # OpenAI-compatible aggregators, keyed by the model string with the
    # "groq/"/"together/"/"fireworks/" routing-namespace prefix already
    # stripped (see ModelRouter._call()/_stream() - that's what actually
    # reaches GenerationResult.model and this function's `model` param).
    "groq": {
        "llama-3.3-70b-versatile": (0.59, 0.79),
    },
    "together": {
        "meta-llama/Llama-3.3-70B-Instruct-Turbo": (0.88, 0.88),
    },
    "fireworks": {
        "accounts/fireworks/models/llama-v3p1-70b-instruct": (0.90, 0.90),
    },
    # ollama is handled as a special case below (local inference — always free)
    # openrouter / azure / bedrock: pricing depends on the underlying model or
    # a private contract - deliberately no entries, so lookups return None.
}


def _lookup_price(provider: str, model: str) -> tuple[float, float] | None:
    table = PRICING_PER_1M_TOKENS.get(provider)
    if not table:
        return None
    if model in table:
        return table[model]
    # Longest-prefix-first so e.g. "gpt-4o-mini" is checked before "gpt-4o".
    for key in sorted(table, key=len, reverse=True):
        if model.startswith(key):
            return table[key]
    return None


def estimate_cost_usd(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    """Estimate the USD cost of one generation call.

    Returns ``0.0`` for ``provider="ollama"`` (self-hosted, no per-token API
    charge). Returns ``None`` — not ``0.0`` — when *provider*/*model* has no
    pricing entry, so callers can distinguish "free by design" from
    "unknown; don't report a misleading number."
    """
    if provider == "ollama":
        return 0.0
    prices = _lookup_price(provider, model)
    if prices is None:
        return None
    input_price, output_price = prices
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price

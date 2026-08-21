"""Normalized reasoning/thinking-effort control across providers.

P7 of the 2026-08-17 gap analysis: reasoning control was Anthropic-only
(``extended_thinking``/``thinking_budget_tokens`` in ``ModelRouter``) even
though several other configured providers natively support some form of
reasoning effort. This normalizes one ``off|low|medium|high|xhigh|max``
ladder into whatever each provider's own knob actually looks like.

Scope (see ``neuralcleave/models/router.py``'s ``generate(thinking=...)``):
    - **anthropic** — native ``extended_thinking`` + a token budget scaled
      by level.
    - **xai**, **openrouter** — both expose the same OpenAI-style
      ``reasoning_effort`` request field (``low``/``medium``/``high``); this
      module's 6-level ladder collapses down to those 3 tiers for them
      (``xhigh``/``max`` both map to ``high``, that API's ceiling).
    - **ollama** — its ``/api/generate``/``/api/chat`` endpoints accept a
      ``think`` field. Some specific models (e.g. ``gpt-oss`` served via
      Ollama) accept a 3-tier string for it, but many reasoning models
      (``deepseek-r1``, etc.) only accept a boolean — NeuralCleave has no
      way to know which kind of model the user pulled, so this collapses
      the ladder to a boolean: ``off`` -> ``False``, everything else ->
      ``True``. That's the honest ceiling of what's safe to send generically.
    - Every other configured provider returns ``{}`` (no-op) — this is a
      deliberate, incremental scope boundary, not an oversight. DeepSeek was
      checked this round (``neuralcleave/models/deepseek.py``): its API has
      no per-request reasoning-effort field at all — the only lever is
      *which model* you call (``deepseek-chat`` vs. ``deepseek-reasoner``),
      already an explicit user config choice via ``cfg.models.*``, not
      something ``/think`` should silently override. Faking a parameter
      DeepSeek's API doesn't accept would just be a different flavor of the
      "looks wired but does nothing" bug this module exists to avoid.

Usage::

    from neuralcleave.models.thinking import resolve_thinking_params

    params = resolve_thinking_params("anthropic", "high")
    # {"extended_thinking": True, "thinking_budget_tokens": 8192}

    params = resolve_thinking_params("xai", "max")
    # {"reasoning_effort": "high"}

    params = resolve_thinking_params("ollama", "low")
    # {"think": True}

    params = resolve_thinking_params("cohere", "high")
    # {} — not supported for this provider, silently ignored by callers
"""

from __future__ import annotations

THINKING_LEVELS: tuple[str, ...] = ("off", "low", "medium", "high", "xhigh", "max")

# Anthropic's own knob: level -> thinking_budget_tokens (ignored when off).
_ANTHROPIC_BUDGET_TOKENS: dict[str, int] = {
    "low": 2048,
    "medium": 4096,
    "high": 8192,
    "xhigh": 16384,
    "max": 32000,
}

# Providers whose OpenAI-compatible endpoint accepts a 3-tier
# reasoning_effort field. xhigh/max collapse to "high" — that API's ceiling.
_OPENAI_STYLE_REASONING_PROVIDERS: tuple[str, ...] = ("xai", "openrouter")
_REASONING_EFFORT_MAP: dict[str, str] = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}


def resolve_thinking_params(provider: str, level: str) -> dict:
    """Map a normalized *level* to *provider*'s own reasoning-control kwargs.

    Raises ValueError for an unrecognized *level* (a programming error, not
    a runtime condition callers should silently swallow). An unsupported
    *provider* is not an error — it just returns ``{}``.
    """
    if level not in THINKING_LEVELS:
        raise ValueError(f"Unknown thinking level: {level!r} (must be one of {THINKING_LEVELS})")

    if provider == "anthropic":
        if level == "off":
            return {"extended_thinking": False, "thinking_budget_tokens": 4096}
        return {"extended_thinking": True, "thinking_budget_tokens": _ANTHROPIC_BUDGET_TOKENS[level]}

    if provider in _OPENAI_STYLE_REASONING_PROVIDERS:
        if level == "off":
            return {}
        return {"reasoning_effort": _REASONING_EFFORT_MAP[level]}

    if provider == "ollama":
        return {"think": level != "off"}

    return {}

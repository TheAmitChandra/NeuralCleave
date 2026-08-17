"""Per-model usage summary — reads ``tokens_total``/``cost_usd_total`` off REGISTRY.

This is a live, in-process view that resets on restart (same lifetime as the
rest of ``REGISTRY``'s counters), not a persisted historical ledger — scrape
``/metrics`` into a real time-series store for long-term history. Backs both
``neuralcleave usage`` (CLI) and ``GET /api/v1/usage`` (REST).
"""

from __future__ import annotations

from neuralcleave.observability.metrics import REGISTRY


def _parse_labels(label_key: str) -> dict[str, str]:
    return dict(pair.split("=", 1) for pair in label_key.split(",") if "=" in pair)


def usage_summary() -> dict[str, dict[str, float]]:
    """Return ``{model: {"input_tokens", "output_tokens", "cost_usd"}}``.

    Aggregates every provider a model name was seen under (a model is keyed
    by name only, matching how ``tokens_total`` is labelled).
    """
    per_model: dict[str, dict[str, float]] = {}

    tokens = REGISTRY.get("tokens_total")
    if tokens is not None:
        for label_key, value in tokens.snapshot().items():
            labels = _parse_labels(label_key)
            model = labels.get("model", "unknown")
            direction = labels.get("direction", "unknown")
            stats = per_model.setdefault(
                model, {"input_tokens": 0.0, "output_tokens": 0.0, "cost_usd": 0.0}
            )
            if direction == "input":
                stats["input_tokens"] += value
            elif direction == "output":
                stats["output_tokens"] += value

    cost = REGISTRY.get("cost_usd_total")
    if cost is not None:
        for label_key, value in cost.snapshot().items():
            labels = _parse_labels(label_key)
            model = labels.get("model", "unknown")
            stats = per_model.setdefault(
                model, {"input_tokens": 0.0, "output_tokens": 0.0, "cost_usd": 0.0}
            )
            stats["cost_usd"] += value

    return per_model

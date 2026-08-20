"""Provider credential + live reachability checks for `neuralcleave models`.

P6 of the 2026-08-17 gap analysis: with 19 configured providers, a solo
operator previously had no first-party way to check "which of my configured
providers actually have working credentials right now" short of trying each
one in a live conversation.

Two tiers:
    - ``configured``: is a key/endpoint present at all? Always computed,
      no network call. ``None`` means "can't be determined generically"
      (Bedrock resolves AWS credentials via boto3's own chain — env vars,
      ``~/.aws/credentials``, instance profile — which NeuralCleave never
      inspects directly).
    - ``reachable`` (only when ``live=True``): an actual HTTP probe against
      the provider's list-models endpoint. Only implemented for providers
      with a well-documented, stable probe endpoint (OpenAI-compatible
      ``GET /v1/models``, or Ollama's native ``GET /api/tags``) — every
      other provider reports ``reachable=None`` with an explicit
      "live check not supported" detail rather than a fabricated result.
      This is a deliberate scope boundary, not an oversight: guessing at
      undocumented or unverified provider endpoints risks exactly the
      "looks configured but doesn't actually work" bug this project has
      hit before.

Usage::

    from neuralcleave.models.health import check_providers

    statuses = await check_providers(router, live=True)
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

# provider -> ModelRouter private key attribute name (or None if no simple
# key attribute applies — see PROVIDER_ORDER's special cases below).
_KEY_ATTR: dict[str, str] = {
    "anthropic": "_anthropic_key",
    "google": "_gemini_key",
    "deepseek": "_deepseek_key",
    "openai": "_openai_key",
    "mistral": "_mistral_key",
    "xai": "_grok_key",
    "cohere": "_cohere_key",
    "moonshot": "_moonshot_key",
    "zhipu": "_glm_key",
    "qwen": "_qwen_key",
    "ernie": "_ernie_key",
    "doubao": "_doubao_key",
    "openrouter": "_openrouter_key",
    "groq": "_groq_key",
    "together": "_together_key",
    "fireworks": "_fireworks_key",
}

# All 19 providers ModelRouter supports, in a stable display order.
PROVIDER_ORDER: tuple[str, ...] = (
    "anthropic", "google", "openai", "deepseek", "ollama", "mistral", "xai",
    "cohere", "moonshot", "zhipu", "qwen", "ernie", "doubao", "openrouter",
    "azure", "bedrock", "groq", "together", "fireworks",
)

# OpenAI-compatible providers with a documented, stable GET /v1/models probe.
_OPENAI_COMPATIBLE_PROBE_BASE_URL: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "xai": "https://api.x.ai/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "deepseek": "https://api.deepseek.com/v1",
}


@dataclass
class ProviderStatus:
    """Credential/reachability status for one provider."""

    provider: str
    configured: bool | None
    live_checked: bool
    reachable: bool | None
    detail: str

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "live_checked": self.live_checked,
            "reachable": self.reachable,
            "detail": self.detail,
        }


def _is_configured(router: object, provider: str) -> bool | None:
    if provider == "ollama":
        return True  # always has a usable default base URL
    if provider == "azure":
        return bool(getattr(router, "_azure_key", "")) and bool(getattr(router, "_azure_endpoint", ""))
    if provider == "bedrock":
        return None  # AWS credentials resolved by boto3's own chain
    attr = _KEY_ATTR.get(provider)
    if attr is None:
        return None
    return bool(getattr(router, attr, ""))


async def _probe_openai_compatible(base_url: str, api_key: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"}
            )
        if resp.status_code == 200:
            return True, "OK"
        if resp.status_code in (401, 403):
            return False, f"HTTP {resp.status_code} — credentials rejected"
        if resp.status_code == 429:
            return False, "HTTP 429 — rate limited"
        return False, f"HTTP {resp.status_code}"
    except httpx.TimeoutException:
        return False, "Request timed out"
    except httpx.HTTPError as exc:
        return False, f"Connection error: {exc}"


async def _probe_ollama(base_url: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
        if resp.status_code == 200:
            return True, "OK"
        return False, f"HTTP {resp.status_code}"
    except httpx.HTTPError as exc:
        return False, f"Connection error: {exc}"


async def _check_one(router: object, provider: str, live: bool) -> ProviderStatus:
    configured = _is_configured(router, provider)

    if not live:
        return ProviderStatus(
            provider=provider, configured=configured, live_checked=False,
            reachable=None, detail="",
        )

    if provider == "ollama":
        reachable, detail = await _probe_ollama(getattr(router, "_ollama_url", "http://localhost:11434"))
        return ProviderStatus(provider=provider, configured=configured, live_checked=True, reachable=reachable, detail=detail)

    probe_base = _OPENAI_COMPATIBLE_PROBE_BASE_URL.get(provider)
    if probe_base is None:
        return ProviderStatus(
            provider=provider, configured=configured, live_checked=False,
            reachable=None, detail="live check not supported for this provider",
        )

    if not configured:
        return ProviderStatus(
            provider=provider, configured=configured, live_checked=False,
            reachable=None, detail="not configured — skipped live check",
        )

    api_key = getattr(router, _KEY_ATTR[provider], "")
    reachable, detail = await _probe_openai_compatible(probe_base, api_key)
    return ProviderStatus(provider=provider, configured=configured, live_checked=True, reachable=reachable, detail=detail)


async def check_providers(router: object, live: bool = False) -> list[ProviderStatus]:
    """Return a :class:`ProviderStatus` for every provider ``ModelRouter`` supports.

    Pass ``live=True`` to also attempt an HTTP probe for providers with a
    supported check (see module docstring) — this makes real network calls
    and should not be run automatically/on a timer.
    """
    return [await _check_one(router, provider, live) for provider in PROVIDER_ORDER]

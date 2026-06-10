"""DeepSeek model provider for CortexFlow v2.

Supports DeepSeek's OpenAI-compatible Chat Completions API endpoint.
Primary models: deepseek-coder (code generation/review), deepseek-chat (general).

The API key is resolved from the *api_key* constructor argument first, then
the DEEPSEEK_API_KEY environment variable.

DeepSeek uses an OpenAI-compatible REST API at https://api.deepseek.com/v1.
This provider uses ``httpx`` (no extra SDK required beyond what CortexFlow
already depends on).

Integration with ModelRouter:
    model IDs starting with "deepseek-" are dispatched to the inline
    ``_deepseek()`` method in router.py. This standalone provider offers the
    same interface as OpenAIProvider and is suitable for direct use or
    future refactoring to unify router dispatch.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Model name constants
# ---------------------------------------------------------------------------

DEEPSEEK_CODER = "deepseek-coder"
DEEPSEEK_CHAT = "deepseek-chat"
DEEPSEEK_REASONER = "deepseek-reasoner"

SUPPORTED_MODELS: frozenset[str] = frozenset({
    DEEPSEEK_CODER,
    DEEPSEEK_CHAT,
    DEEPSEEK_REASONER,
    "deepseek-coder-v2",
    "deepseek-v2",
})

_BASE_URL = "https://api.deepseek.com/v1/chat/completions"


# ---------------------------------------------------------------------------
# Response type
# ---------------------------------------------------------------------------


@dataclass
class DeepSeekResponse:
    """Typed result from a DeepSeek chat completion."""

    text: str
    model: str
    usage: dict[str, Any]

    @property
    def input_tokens(self) -> int:
        return int(self.usage.get("input_tokens", 0))

    @property
    def output_tokens(self) -> int:
        return int(self.usage.get("output_tokens", 0))


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class DeepSeekProvider:
    """Async wrapper around DeepSeek's OpenAI-compatible Chat Completions API.

    Usage::

        provider = DeepSeekProvider(api_key="sk-…")
        result   = await provider.generate(
            "Write a Python function to reverse a linked list.",
            model=DEEPSEEK_CODER,
        )
        print(result.text)
    """

    def __init__(
        self,
        api_key: str = "",
        default_model: str = DEEPSEEK_CODER,
        timeout: float = 60.0,
        max_tokens: int = 4096,
    ) -> None:
        self._api_key: str = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self._default_model: str = default_model
        self._timeout: float = timeout
        self._max_tokens: int = max_tokens

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> DeepSeekResponse:
        """Send *prompt* to DeepSeek and return the typed response.

        Args:
            prompt:      User-turn content.
            model:       Override the default model for this call.
            system:      Optional system-turn content.
            temperature: Sampling temperature. DeepSeek Coder defaults to 0.0
                         for deterministic code generation.

        Raises:
            RuntimeError: If the ``httpx`` package is not installed or the API
                          key is missing.
            httpx.HTTPStatusError: Propagated from the underlying HTTP client.
        """
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx package required: pip install httpx") from exc

        if not self._api_key:
            raise RuntimeError(
                "DeepSeek API key missing — set DEEPSEEK_API_KEY or pass api_key="
            )

        chosen_model = model or self._default_model
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": chosen_model,
                    "messages": messages,
                    "max_tokens": self._max_tokens,
                    "temperature": temperature,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()

        text = (data["choices"][0]["message"]["content"] or "").strip()
        raw_usage = data.get("usage", {})
        usage: dict[str, Any] = {
            "input_tokens": raw_usage.get("prompt_tokens", 0),
            "output_tokens": raw_usage.get("completion_tokens", 0),
        }
        return DeepSeekResponse(text=text, model=chosen_model, usage=usage)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """True when an API key is present."""
        return bool(self._api_key)

    @property
    def default_model(self) -> str:
        return self._default_model

    @staticmethod
    def get_supported_models() -> frozenset[str]:
        return SUPPORTED_MODELS

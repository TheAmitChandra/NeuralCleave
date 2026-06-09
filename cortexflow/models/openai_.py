"""OpenAI GPT-4 / GPT-4o model provider for CortexFlow v2.

Supports the full gpt-4 family: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-4,
gpt-3.5-turbo. Uses the async openai client (openai >= 1.0).

The API key is resolved from the *api_key* constructor argument first, then
the OPENAI_API_KEY environment variable.

Integration with ModelRouter:
    model IDs starting with "gpt-" in the routing table are dispatched here
    via _call(). See router.py for the dispatch hook.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Model name constants (mirrors router.py convention)
# ---------------------------------------------------------------------------

GPT4O = "gpt-4o"
GPT4O_MINI = "gpt-4o-mini"
GPT4_TURBO = "gpt-4-turbo"
GPT4 = "gpt-4"
GPT35_TURBO = "gpt-3.5-turbo"

SUPPORTED_MODELS: frozenset[str] = frozenset({
    GPT4O,
    GPT4O_MINI,
    GPT4_TURBO,
    GPT4,
    GPT35_TURBO,
})


# ---------------------------------------------------------------------------
# Response type
# ---------------------------------------------------------------------------


@dataclass
class OpenAIResponse:
    """Typed result from an OpenAI chat completion."""

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


class OpenAIProvider:
    """Async wrapper around OpenAI's Chat Completions API.

    Usage::

        provider = OpenAIProvider(api_key="sk-…")
        result   = await provider.generate("Explain quantum entanglement.")
        print(result.text)
    """

    def __init__(
        self,
        api_key: str = "",
        default_model: str = GPT4O,
        timeout: float = 30.0,
        max_tokens: int = 4096,
    ) -> None:
        self._api_key: str = api_key or os.getenv("OPENAI_API_KEY", "")
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
        temperature: float = 0.7,
    ) -> OpenAIResponse:
        """Send *prompt* to OpenAI and return the typed response.

        Args:
            prompt:      User-turn content.
            model:       Override the default model for this call.
            system:      Optional system-turn content.
            temperature: Sampling temperature (0.0–2.0).

        Raises:
            RuntimeError: If the ``openai`` package is not installed.
            openai.APIError: Propagated from the underlying client.
        """
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package required: pip install openai"
            ) from exc

        chosen_model = model or self._default_model
        client = AsyncOpenAI(api_key=self._api_key, timeout=self._timeout)

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=chosen_model,
            messages=messages,
            temperature=temperature,
            max_tokens=self._max_tokens,
        )

        content = (response.choices[0].message.content or "").strip()
        raw_usage = response.usage
        usage: dict[str, Any] = {
            "input_tokens": raw_usage.prompt_tokens if raw_usage else 0,
            "output_tokens": raw_usage.completion_tokens if raw_usage else 0,
        }
        return OpenAIResponse(text=content, model=chosen_model, usage=usage)

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

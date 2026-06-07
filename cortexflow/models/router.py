"""Task-aware LLM model router with automatic fallback chain.

Routes each generation request to the optimal provider based on task type,
then falls back through the chain if the primary provider fails.

Routing table:
    complex_reasoning  → Claude Opus 4.8  → Gemini Pro
    code_generation    → DeepSeek Coder   → Claude Sonnet
    code_review        → DeepSeek Coder   → Gemini Flash
    summarization      → Gemini Flash     → Ollama
    intent_extraction  → Gemini Flash     → Ollama
    task_decomposition → Claude Sonnet    → Gemini Pro
    cheap_inference    → Ollama           → Gemini Flash
    general (default)  → Gemini Flash     → Ollama
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider name constants
# ---------------------------------------------------------------------------

CLAUDE_OPUS = "claude-opus-4-8"
CLAUDE_SONNET = "claude-sonnet-4-6"
GEMINI_PRO = "gemini-1.5-pro"
GEMINI_FLASH = "gemini-2.0-flash"
DEEPSEEK_CODER = "deepseek-coder"
OLLAMA_DEFAULT = "ollama/llama3.2"

# ---------------------------------------------------------------------------
# Routing table: task_type → [primary, fallback, ...]
# ---------------------------------------------------------------------------

_ROUTING: dict[str, list[str]] = {
    "complex_reasoning": [CLAUDE_OPUS, GEMINI_PRO, OLLAMA_DEFAULT],
    "code_generation": [DEEPSEEK_CODER, CLAUDE_SONNET, GEMINI_FLASH],
    "code_review": [DEEPSEEK_CODER, GEMINI_FLASH, OLLAMA_DEFAULT],
    "summarization": [GEMINI_FLASH, OLLAMA_DEFAULT],
    "intent_extraction": [GEMINI_FLASH, OLLAMA_DEFAULT],
    "task_decomposition": [CLAUDE_SONNET, GEMINI_PRO, OLLAMA_DEFAULT],
    "reflection": [GEMINI_FLASH, OLLAMA_DEFAULT],
    "validation": [GEMINI_FLASH, OLLAMA_DEFAULT],
    "cheap_inference": [OLLAMA_DEFAULT, GEMINI_FLASH],
    "general": [GEMINI_FLASH, OLLAMA_DEFAULT],
}


@dataclass
class GenerationResult:
    """Result from a successful LLM generation."""

    text: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)


class ModelRouter:
    """Routes generation requests to the optimal LLM provider.

    Falls back through the provider chain automatically on errors.

    Usage::

        router = ModelRouter()
        result = await router.generate(
            prompt="Summarise this article...",
            task_type="summarization",
        )
        print(result.text)
    """

    def __init__(
        self,
        *,
        anthropic_api_key: str | None = None,
        gemini_api_key: str | None = None,
        deepseek_api_key: str | None = None,
        ollama_base_url: str = "http://localhost:11434",
    ) -> None:
        self._anthropic_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._gemini_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self._deepseek_key = deepseek_api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self._ollama_url = ollama_base_url

    async def generate(
        self,
        prompt: str,
        *,
        task_type: str = "general",
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> GenerationResult:
        """Generate text using the best available provider for the given task.

        Tries providers in priority order; raises RuntimeError if all fail.
        """
        chain = _ROUTING.get(task_type, _ROUTING["general"])
        last_error: Exception | None = None

        for model_id in chain:
            try:
                result = await self._call(
                    model_id,
                    prompt=prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                logger.info(
                    "model.generate task=%s model=%s tokens=%s",
                    task_type,
                    model_id,
                    result.usage.get("output_tokens", "?"),
                )
                return result
            except Exception as exc:
                logger.warning("model.%s failed, trying next: %s", model_id, exc)
                last_error = exc

        raise RuntimeError(
            f"All providers exhausted for task_type={task_type!r}. Last error: {last_error}"
        )

    async def _call(
        self,
        model_id: str,
        *,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
    ) -> GenerationResult:
        if model_id.startswith("claude-"):
            return await self._claude(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        if model_id.startswith("gemini-"):
            return await self._gemini(model_id, prompt=prompt, system=system, max_tokens=max_tokens)
        if model_id.startswith("deepseek-"):
            return await self._deepseek(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        if model_id.startswith("ollama/"):
            return await self._ollama(
                model_id[7:], prompt=prompt, system=system, max_tokens=max_tokens
            )
        raise ValueError(f"Unknown model prefix: {model_id!r}")

    async def _claude(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> GenerationResult:
        try:
            import anthropic  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install anthropic")

        if not self._anthropic_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        client = anthropic.AsyncAnthropic(api_key=self._anthropic_key)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = await client.messages.create(**kwargs)
        text = response.content[0].text if response.content else ""
        return GenerationResult(
            text=text,
            model=model,
            provider="anthropic",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    async def _gemini(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int
    ) -> GenerationResult:
        try:
            import google.generativeai as genai  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install google-generativeai")

        if not self._gemini_key:
            raise RuntimeError("GEMINI_API_KEY not set")

        genai.configure(api_key=self._gemini_key)
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        gmodel = genai.GenerativeModel(model)
        response = await gmodel.generate_content_async(
            full_prompt,
            generation_config=genai.GenerationConfig(max_output_tokens=max_tokens),
        )
        return GenerationResult(
            text=response.text,
            model=model,
            provider="google",
        )

    async def _deepseek(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> GenerationResult:
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install httpx")

        if not self._deepseek_key:
            raise RuntimeError("DEEPSEEK_API_KEY not set")

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._deepseek_key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return GenerationResult(
            text=text,
            model=model,
            provider="deepseek",
            usage={
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
        )

    async def _ollama(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int
    ) -> GenerationResult:
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install httpx")

        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._ollama_url}/api/generate",
                json={"model": model, "prompt": full_prompt, "stream": False},
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()

        return GenerationResult(
            text=data.get("response", ""),
            model=model,
            provider="ollama",
        )


# Module-level singleton
model_router = ModelRouter()

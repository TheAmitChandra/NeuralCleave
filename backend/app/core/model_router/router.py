"""Model router — intelligent routing to the right LLM with automatic fallback chain.

Routing table:
  complex_reasoning  → Gemini Pro
  code_generation    → DeepSeek Coder
  summarization      → Gemini Flash
  embeddings         → sentence-transformers (local)
  cheap_inference    → Ollama (local)

Fallback chain: Gemini → DeepSeek → Ollama → DEGRADED MODE
"""

from __future__ import annotations

import structlog
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from app.core.model_router.deepseek import DeepSeekClient
from app.core.model_router.gemini import GeminiClient
from app.core.model_router.ollama import OllamaClient

logger = structlog.get_logger(__name__)

# Task type → preferred provider
_ROUTING_TABLE: dict[str, str] = {
    "complex_reasoning": "gemini_pro",
    "code_generation": "deepseek_coder",
    "code_review": "deepseek_coder",
    "summarization": "gemini_flash",
    "intent_extraction": "gemini_flash",
    "task_decomposition": "gemini_pro",
    "validation": "gemini_flash",
    "reflection": "gemini_flash",
    "cheap_inference": "ollama",
    "general": "gemini_flash",
}

# Providers in fallback order
_FALLBACK_ORDER = ["gemini_flash", "gemini_pro", "deepseek_coder", "ollama"]


class ModelRouter:
    """Central LLM router — picks the right model, falls back on failure."""

    def __init__(self) -> None:
        self._gemini_pro = GeminiClient(model="gemini-1.5-pro")
        self._gemini_flash = GeminiClient(model="gemini-2.0-flash")
        self._deepseek = DeepSeekClient(model="deepseek-coder")
        self._ollama = OllamaClient()

    def _get_client(self, provider: str) -> GeminiClient | DeepSeekClient | OllamaClient:
        return {
            "gemini_pro": self._gemini_pro,
            "gemini_flash": self._gemini_flash,
            "deepseek_coder": self._deepseek,
            "ollama": self._ollama,
        }[provider]

    async def generate(
        self,
        prompt: str,
        task_type: str = "general",
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> str:
        """Route to the preferred provider and fall back down the chain on failure."""
        preferred = _ROUTING_TABLE.get(task_type, "gemini_flash")

        # Build fallback list starting from the preferred provider
        providers = [preferred] + [p for p in _FALLBACK_ORDER if p != preferred]

        last_error: Exception | None = None
        for provider in providers:
            try:
                client = self._get_client(provider)
                logger.info("model_router_attempt", provider=provider, task_type=task_type)
                return await client.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    task_type=task_type,
                )
            except Exception as exc:
                logger.warning(
                    "model_router_provider_failed",
                    provider=provider,
                    error=str(exc),
                )
                last_error = exc

        # All providers exhausted → DEGRADED MODE
        logger.error("model_router_all_providers_failed", task_type=task_type)
        raise RuntimeError(
            f"All LLM providers failed for task_type='{task_type}'. Last error: {last_error}"
        )

    async def generate_structured(
        self,
        prompt: str,
        response_schema: dict,
        task_type: str = "general",
        system_instruction: str | None = None,
        temperature: float = 0.1,
    ) -> dict:
        """Generate structured JSON output — Gemini only (supports JSON mode natively)."""
        return await self._gemini_flash.generate_structured(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
            temperature=temperature,
        )


# Singleton — import and use this across the application
model_router = ModelRouter()

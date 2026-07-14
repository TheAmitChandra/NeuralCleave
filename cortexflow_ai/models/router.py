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

Phase 4 additions:
    - Auto complexity detection: short/simple → fast model, long/complex → Opus
    - Privacy mode: all calls routed to local Ollama (zero external API calls)
    - Per-channel model override: channel_overrides dict pins a channel to a model
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider name constants
# ---------------------------------------------------------------------------

CLAUDE_OPUS = "claude-opus-4-8"
CLAUDE_SONNET = "claude-sonnet-4-6"
# Bumped from gemini-1.5-pro / gemini-2.0-flash, both confirmed (live,
# against a real API key) to have zero free-tier quota — Google has moved
# the free tier onto the 2.5 generation. gemini-2.5-flash verified working
# on the free tier; gemini-2.5-pro requires a paid plan (expected for a
# "Pro" tier model, unlike 2.0-flash's quota loss which was a real
# regression for existing callers).
GEMINI_PRO = "gemini-2.5-pro"
GEMINI_FLASH = "gemini-2.5-flash"
DEEPSEEK_CODER = "deepseek-coder"
OLLAMA_DEFAULT = "ollama/llama3.2:1b"
GPT4O = "gpt-4o"
GPT4O_MINI = "gpt-4o-mini"

# Mistral AI
MISTRAL_LARGE = "mistral-large-latest"
MISTRAL_SMALL = "mistral-small-latest"

# xAI (Grok)
GROK_3 = "grok-3"
GROK_3_MINI = "grok-3-mini"

# Cohere
COMMAND_R_PLUS = "command-r-plus"
COMMAND_R = "command-r"

# Moonshot AI (Kimi)
MOONSHOT_8K = "moonshot-v1-8k"
MOONSHOT_32K = "moonshot-v1-32k"

# Zhipu AI (GLM / BigModel)
GLM_4 = "glm-4"
GLM_4_FLASH = "glm-4-flash"

# Alibaba Cloud (Qwen / DashScope)
QWEN_MAX = "qwen-max"
QWEN_TURBO = "qwen-turbo"

# Baidu (ERNIE / Qianfan)
ERNIE_BOT_4 = "ernie-bot-4"
ERNIE_SPEED = "ernie-speed"

# ByteDance (Doubao / Ark)
DOUBAO_PRO = "doubao-pro-32k"
DOUBAO_LITE = "doubao-lite-32k"

# ---------------------------------------------------------------------------
# Routing table: task_type → [primary, fallback, ...]
# ---------------------------------------------------------------------------

_ROUTING: dict[str, list[str]] = {
    "complex_reasoning": [CLAUDE_OPUS, GPT4O, GROK_3, GEMINI_PRO, MISTRAL_LARGE, OLLAMA_DEFAULT],
    "code_generation": [DEEPSEEK_CODER, CLAUDE_SONNET, GPT4O, QWEN_MAX, GEMINI_FLASH],
    "code_review": [DEEPSEEK_CODER, GPT4O, QWEN_MAX, GEMINI_FLASH, OLLAMA_DEFAULT],
    "summarization": [GEMINI_FLASH, COMMAND_R_PLUS, GPT4O_MINI, MOONSHOT_8K, OLLAMA_DEFAULT],
    "intent_extraction": [GEMINI_FLASH, GLM_4_FLASH, GPT4O_MINI, OLLAMA_DEFAULT],
    "task_decomposition": [CLAUDE_SONNET, GPT4O, GEMINI_PRO, MISTRAL_LARGE, OLLAMA_DEFAULT],
    "reflection": [GEMINI_FLASH, GPT4O_MINI, OLLAMA_DEFAULT],
    "validation": [GEMINI_FLASH, GPT4O_MINI, OLLAMA_DEFAULT],
    "cheap_inference": [OLLAMA_DEFAULT, GLM_4_FLASH, DOUBAO_LITE, GPT4O_MINI, GEMINI_FLASH],
    "general": [GEMINI_FLASH, GPT4O_MINI, COMMAND_R, MOONSHOT_8K, OLLAMA_DEFAULT],
}

# Map friendly provider names (as stored in Settings UI) to model IDs.
# Used by the forced_provider override so the UI can say "gemini" instead
# of "gemini-2.5-flash".
_PROVIDER_TO_MODEL: dict[str, str] = {
    "gemini": GEMINI_FLASH,
    "anthropic": CLAUDE_SONNET,
    "openai": GPT4O_MINI,
    "deepseek": DEEPSEEK_CODER,
    "ollama": OLLAMA_DEFAULT,
    "mistral": MISTRAL_LARGE,
    "grok": GROK_3,
    "xai": GROK_3,
    "cohere": COMMAND_R_PLUS,
    "moonshot": MOONSHOT_8K,
    "kimi": MOONSHOT_8K,
    "glm": GLM_4,
    "zhipu": GLM_4,
    "qwen": QWEN_MAX,
    "alibaba": QWEN_MAX,
    "ernie": ERNIE_BOT_4,
    "baidu": ERNIE_BOT_4,
    "doubao": DOUBAO_PRO,
    "bytedance": DOUBAO_PRO,
}

# ---------------------------------------------------------------------------
# Complexity detection thresholds
# ---------------------------------------------------------------------------

# Prompts above this word count are routed to complex_reasoning
_COMPLEX_WORD_THRESHOLD = 200

# Keywords that indicate a complex reasoning task regardless of length
_COMPLEX_KEYWORDS = frozenset({
    "analyse", "analyze", "compare", "critique", "evaluate", "explain",
    "reason", "why", "how does", "research", "investigate", "debate",
    "pros and cons", "tradeoffs", "trade-offs", "implications",
})

# Short prompts (below this word count) use cheap_inference
_SHORT_WORD_THRESHOLD = 20


@dataclass
class GenerationResult:
    """Result from a successful LLM generation."""

    text: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    thinking: str | None = None  # Claude extended thinking trace, if requested


@dataclass
class StreamChunk:
    """One increment of a streaming generation.

    Every provider stream yields zero or more chunks with ``text`` set and
    ``done=False``, followed by exactly one final chunk with ``done=True``
    carrying ``model``/``provider``/``usage`` (and ``error`` if the stream
    failed partway through, after content had already been yielded).
    """

    text: str = ""
    done: bool = False
    model: str | None = None
    provider: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    error: str | None = None


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
        openai_api_key: str | None = None,
        ollama_base_url: str = "http://localhost:11434",
        mistral_api_key: str | None = None,
        grok_api_key: str | None = None,
        cohere_api_key: str | None = None,
        moonshot_api_key: str | None = None,
        glm_api_key: str | None = None,
        qwen_api_key: str | None = None,
        ernie_api_key: str | None = None,
        doubao_api_key: str | None = None,
        privacy_mode: bool = False,
        channel_overrides: dict[str, str] | None = None,
        auto_complexity: bool = True,
    ) -> None:
        self._anthropic_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._gemini_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self._deepseek_key = deepseek_api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self._openai_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self._ollama_url = ollama_base_url
        self._mistral_key = mistral_api_key or os.getenv("MISTRAL_API_KEY", "")
        self._grok_key = grok_api_key or os.getenv("XAI_API_KEY", "")
        self._cohere_key = cohere_api_key or os.getenv("COHERE_API_KEY", "")
        self._moonshot_key = moonshot_api_key or os.getenv("MOONSHOT_API_KEY", "")
        self._glm_key = glm_api_key or os.getenv("ZHIPUAI_API_KEY", "")
        self._qwen_key = qwen_api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self._ernie_key = ernie_api_key or os.getenv("QIANFAN_API_KEY", "")
        self._doubao_key = doubao_api_key or os.getenv("ARK_API_KEY", "")
        # Phase 4: privacy mode, per-channel overrides, auto complexity
        self.privacy_mode = privacy_mode
        self._channel_overrides: dict[str, str] = channel_overrides or {}
        self.auto_complexity = auto_complexity
        # Optional forced provider: when set, every request is routed to this
        # provider first (followed by the normal fallback chain). Set at runtime
        # via POST /api/v1/settings/model {"provider": "gemini"}.
        self._forced_provider: str | None = None

    async def generate(
        self,
        prompt: str,
        *,
        task_type: str = "general",
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        channel_id: str | None = None,
        extended_thinking: bool = False,
        thinking_budget_tokens: int = 4096,
    ) -> GenerationResult:
        """Generate text using the best available provider for the given task.

        Args:
            prompt:     The user prompt.
            task_type:  Task hint for routing. If ``auto_complexity`` is True and
                        task_type is "general", the prompt is analysed and the
                        task_type may be upgraded to "complex_reasoning" or
                        downgraded to "cheap_inference".
            system:     Optional system prompt.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature. Ignored (forced to 1.0) when
                        extended_thinking is True, per the Anthropic API.
            channel_id: If provided, checked against channel_overrides to pin a
                        specific model.
            extended_thinking: Enable Claude's extended thinking mode. Only
                        has an effect when the resolved model is a Claude
                        model — silently ignored for other providers.
            thinking_budget_tokens: Token budget reserved for the thinking
                        trace when extended_thinking is True. Must be less
                        than max_tokens.

        Tries providers in priority order; raises RuntimeError if all fail.
        """
        chain = self._resolve_chain(prompt, task_type=task_type, channel_id=channel_id)

        last_error: Exception | None = None

        for model_id in chain:
            try:
                result = await self._call(
                    model_id,
                    prompt=prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    extended_thinking=extended_thinking,
                    thinking_budget_tokens=thinking_budget_tokens,
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

    def _resolve_chain(
        self,
        prompt: str,
        *,
        task_type: str,
        channel_id: str | None,
    ) -> list[str]:
        """Shared routing logic between generate() and generate_stream()."""
        if self.privacy_mode:
            logger.debug("model.privacy_mode prompt_len=%d", len(prompt))
            return [OLLAMA_DEFAULT]
        if channel_id and channel_id in self._channel_overrides:
            override_model = self._channel_overrides[channel_id]
            logger.debug("model.channel_override channel=%s model=%s", channel_id, override_model)
            return [override_model, *_ROUTING.get("general", [])]
        if self._forced_provider is not None:
            # Map provider name (e.g. "gemini") to a concrete model ID using
            # the routing table's general-task chain as the pool.
            forced = _PROVIDER_TO_MODEL.get(self._forced_provider, self._forced_provider)
            general_chain = list(_ROUTING.get("general", []))
            # Put the forced model first; keep the rest as fallbacks.
            fallbacks = [m for m in general_chain if m != forced]
            logger.debug("model.forced_provider provider=%s model=%s", self._forced_provider, forced)
            return [forced, *fallbacks]
        if self.auto_complexity and task_type == "general":
            task_type = _detect_complexity(prompt)
            if task_type != "general":
                logger.debug("model.complexity_detected task=%s", task_type)
        return _ROUTING.get(task_type, _ROUTING["general"])

    async def generate_stream(
        self,
        prompt: str,
        *,
        task_type: str = "general",
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        channel_id: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming counterpart to generate().

        Yields StreamChunk objects as text arrives; the final chunk has
        done=True with usage/model/provider populated.

        Falls back to the next provider in the chain only if a provider
        fails before yielding any text. Once partial output has reached the
        caller, a mid-stream failure surfaces as a done=True error chunk
        instead of silently retrying — retrying at that point would
        duplicate or contradict text the caller may have already shown.
        Extended thinking is not supported in the streaming path.
        """
        chain = self._resolve_chain(prompt, task_type=task_type, channel_id=channel_id)

        last_error: Exception | None = None
        for model_id in chain:
            yielded_any = False
            try:
                async for chunk in self._call_stream(
                    model_id,
                    prompt=prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ):
                    yielded_any = True
                    yield chunk
                return
            except Exception as exc:
                if yielded_any:
                    logger.error("model.%s failed mid-stream: %s", model_id, exc)
                    yield StreamChunk(done=True, model=model_id, error=str(exc))
                    return
                logger.warning("model.%s failed, trying next: %s", model_id, exc)
                last_error = exc

        raise RuntimeError(
            f"All providers exhausted for task_type={task_type!r}. Last error: {last_error}"
        )

    async def _call_stream(
        self,
        model_id: str,
        *,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[StreamChunk]:
        if model_id.startswith("claude-"):
            stream = self._claude_stream(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        elif model_id.startswith("gemini-"):
            stream = self._gemini_stream(model_id, prompt=prompt, system=system, max_tokens=max_tokens)
        elif model_id.startswith("deepseek-"):
            stream = self._deepseek_stream(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        elif model_id.startswith("ollama/"):
            stream = self._ollama_stream(model_id[7:], prompt=prompt, system=system, max_tokens=max_tokens)
        elif model_id.startswith("gpt-"):
            stream = self._openai_stream(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        elif model_id.startswith("mistral-"):
            stream = self._mistral_stream(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        elif model_id.startswith("grok-"):
            stream = self._grok_stream(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        elif model_id.startswith("command-"):
            stream = self._cohere_stream(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        elif model_id.startswith("moonshot-"):
            stream = self._moonshot_stream(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        elif model_id.startswith("glm-"):
            stream = self._glm_stream(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        elif model_id.startswith("qwen-"):
            stream = self._qwen_stream(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        elif model_id.startswith("ernie-"):
            stream = self._ernie_stream(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        elif model_id.startswith("doubao-"):
            stream = self._doubao_stream(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        else:
            raise ValueError(f"Unknown model prefix: {model_id!r}")

        async for chunk in stream:
            yield chunk

    async def _call(
        self,
        model_id: str,
        *,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
        extended_thinking: bool = False,
        thinking_budget_tokens: int = 4096,
    ) -> GenerationResult:
        if model_id.startswith("claude-"):
            return await self._claude(
                model_id,
                prompt=prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                extended_thinking=extended_thinking,
                thinking_budget_tokens=thinking_budget_tokens,
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
        if model_id.startswith("gpt-"):
            return await self._openai(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        if model_id.startswith("mistral-"):
            return await self._mistral(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        if model_id.startswith("grok-"):
            return await self._grok(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        if model_id.startswith("command-"):
            return await self._cohere(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        if model_id.startswith("moonshot-"):
            return await self._moonshot(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        if model_id.startswith("glm-"):
            return await self._glm(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        if model_id.startswith("qwen-"):
            return await self._qwen(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        if model_id.startswith("ernie-"):
            return await self._ernie(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        if model_id.startswith("doubao-"):
            return await self._doubao(
                model_id, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature
            )
        raise ValueError(f"Unknown model prefix: {model_id!r}")

    async def _claude(
        self,
        model: str,
        *,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
        extended_thinking: bool = False,
        thinking_budget_tokens: int = 4096,
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
            # The Anthropic API requires temperature=1 when thinking is enabled.
            "temperature": 1.0 if extended_thinking else temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        if extended_thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget_tokens}

        response = await client.messages.create(**kwargs)
        text = ""
        thinking_text: str | None = None
        for block in response.content or []:
            block_type = getattr(block, "type", "text")
            if block_type == "thinking":
                thinking_text = getattr(block, "thinking", None)
            elif block_type == "text":
                text = getattr(block, "text", "")

        return GenerationResult(
            text=text,
            model=model,
            provider="anthropic",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            thinking=thinking_text,
        )

    async def _claude_stream(
        self,
        model: str,
        *,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[StreamChunk]:
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

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(text=text, model=model, provider="anthropic")
            final = await stream.get_final_message()

        yield StreamChunk(
            done=True,
            model=model,
            provider="anthropic",
            usage={
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
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
        usage: dict[str, int] = {}
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata is not None:
            usage = {
                "input_tokens": getattr(usage_metadata, "prompt_token_count", 0) or 0,
                "output_tokens": getattr(usage_metadata, "candidates_token_count", 0) or 0,
            }
        return GenerationResult(
            text=response.text,
            model=model,
            provider="google",
            usage=usage,
        )

    async def _gemini_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int
    ) -> AsyncIterator[StreamChunk]:
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
            stream=True,
        )

        usage: dict[str, int] = {}
        async for chunk in response:
            usage_metadata = getattr(chunk, "usage_metadata", None)
            if usage_metadata is not None:
                usage = {
                    "input_tokens": getattr(usage_metadata, "prompt_token_count", 0) or 0,
                    "output_tokens": getattr(usage_metadata, "candidates_token_count", 0) or 0,
                }
            text = getattr(chunk, "text", "") or ""
            if text:
                yield StreamChunk(text=text, model=model, provider="google")

        yield StreamChunk(done=True, model=model, provider="google", usage=usage)

    async def _deepseek(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> GenerationResult:
        from cortexflow_ai.models.deepseek import DeepSeekProvider

        if not self._deepseek_key:
            raise RuntimeError("DEEPSEEK_API_KEY not set")

        provider = DeepSeekProvider(
            api_key=self._deepseek_key,
            default_model=model,
            max_tokens=max_tokens,
        )
        response = await provider.generate(
            prompt, model=model, system=system, temperature=temperature
        )
        return GenerationResult(
            text=response.text,
            model=model,
            provider="deepseek",
            usage=response.usage,
        )

    async def _deepseek_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> AsyncIterator[StreamChunk]:
        """Streams via DeepSeek's raw OpenAI-compatible SSE endpoint.

        DeepSeekProvider (models/deepseek.py) has no streaming method, so
        this talks to the same REST endpoint directly with stream=True,
        parsing Server-Sent Events lines by hand (no extra SDK needed,
        consistent with DeepSeekProvider's own httpx-only approach).
        """
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

        usage: dict[str, int] = {}
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._deepseek_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True,
                },
                timeout=60.0,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):].strip()
                    if payload == "[DONE]":
                        break
                    chunk_data = json.loads(payload)
                    choices = chunk_data.get("choices") or [{}]
                    text = (choices[0].get("delta") or {}).get("content") or ""
                    chunk_usage = chunk_data.get("usage")
                    if chunk_usage:
                        usage = {
                            "input_tokens": chunk_usage.get("prompt_tokens", 0),
                            "output_tokens": chunk_usage.get("completion_tokens", 0),
                        }
                    if text:
                        yield StreamChunk(text=text, model=model, provider="deepseek")

        yield StreamChunk(done=True, model=model, provider="deepseek", usage=usage)

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
                json={"model": model, "prompt": full_prompt, "stream": False,
                      "options": {"num_predict": max_tokens}},
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()

        usage: dict[str, int] = {}
        if "prompt_eval_count" in data or "eval_count" in data:
            usage = {
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
            }

        return GenerationResult(
            text=data.get("response", ""),
            model=model,
            provider="ollama",
            usage=usage,
        )

    async def _ollama_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int
    ) -> AsyncIterator[StreamChunk]:
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install httpx")

        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self._ollama_url}/api/generate",
                json={"model": model, "prompt": full_prompt, "stream": True,
                      "options": {"num_predict": max_tokens}},
                timeout=120.0,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    text = data.get("response", "")
                    if data.get("done"):
                        usage: dict[str, int] = {}
                        if "prompt_eval_count" in data or "eval_count" in data:
                            usage = {
                                "input_tokens": data.get("prompt_eval_count", 0),
                                "output_tokens": data.get("eval_count", 0),
                            }
                        if text:
                            yield StreamChunk(text=text, model=model, provider="ollama")
                        yield StreamChunk(done=True, model=model, provider="ollama", usage=usage)
                    elif text:
                        yield StreamChunk(text=text, model=model, provider="ollama")

    async def _openai(
        self,
        model: str,
        *,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
    ) -> GenerationResult:
        from cortexflow_ai.models.openai_ import OpenAIProvider

        if not self._openai_key:
            raise RuntimeError("OPENAI_API_KEY not set")

        provider = OpenAIProvider(
            api_key=self._openai_key,
            default_model=model,
            max_tokens=max_tokens,
        )
        response = await provider.generate(
            prompt, model=model, system=system, temperature=temperature
        )
        return GenerationResult(
            text=response.text,
            model=model,
            provider="openai",
            usage=response.usage,
        )

    async def _openai_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> AsyncIterator[StreamChunk]:
        try:
            from openai import AsyncOpenAI  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("openai package required: pip install openai") from exc

        if not self._openai_key:
            raise RuntimeError("OPENAI_API_KEY not set")

        client = AsyncOpenAI(api_key=self._openai_key)
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        usage: dict[str, int] = {}
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = {
                    "input_tokens": chunk_usage.prompt_tokens or 0,
                    "output_tokens": chunk_usage.completion_tokens or 0,
                }
            if not chunk.choices:
                continue
            text = chunk.choices[0].delta.content or ""
            if text:
                yield StreamChunk(text=text, model=model, provider="openai")

        yield StreamChunk(done=True, model=model, provider="openai", usage=usage)

    # ------------------------------------------------------------------
    # Generic OpenAI-compatible provider helpers
    # ------------------------------------------------------------------

    async def _compat_call(
        self,
        model: str,
        *,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
        base_url: str,
        api_key: str,
        provider: str,
    ) -> GenerationResult:
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install httpx")

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
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

        text = data["choices"][0]["message"]["content"] or ""
        usage_raw = data.get("usage") or {}
        usage = {
            "input_tokens": usage_raw.get("prompt_tokens", 0),
            "output_tokens": usage_raw.get("completion_tokens", 0),
        }
        return GenerationResult(text=text, model=model, provider=provider, usage=usage)

    async def _compat_stream(
        self,
        model: str,
        *,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
        base_url: str,
        api_key: str,
        provider: str,
    ) -> AsyncIterator[StreamChunk]:
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install httpx")

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        usage: dict[str, int] = {}
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True,
                },
                timeout=60.0,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):].strip()
                    if payload == "[DONE]":
                        break
                    chunk_data = json.loads(payload)
                    choices = chunk_data.get("choices") or [{}]
                    text = (choices[0].get("delta") or {}).get("content") or ""
                    chunk_usage = chunk_data.get("usage")
                    if chunk_usage:
                        usage = {
                            "input_tokens": chunk_usage.get("prompt_tokens", 0),
                            "output_tokens": chunk_usage.get("completion_tokens", 0),
                        }
                    if text:
                        yield StreamChunk(text=text, model=model, provider=provider)

        yield StreamChunk(done=True, model=model, provider=provider, usage=usage)

    # ------------------------------------------------------------------
    # Mistral AI  (api.mistral.ai — OpenAI-compat)
    # ------------------------------------------------------------------

    async def _mistral(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> GenerationResult:
        if not self._mistral_key:
            raise RuntimeError("MISTRAL_API_KEY not set")
        return await self._compat_call(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://api.mistral.ai/v1", api_key=self._mistral_key, provider="mistral",
        )

    async def _mistral_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> AsyncIterator[StreamChunk]:
        if not self._mistral_key:
            raise RuntimeError("MISTRAL_API_KEY not set")
        async for chunk in self._compat_stream(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://api.mistral.ai/v1", api_key=self._mistral_key, provider="mistral",
        ):
            yield chunk

    # ------------------------------------------------------------------
    # xAI Grok  (api.x.ai — OpenAI-compat)
    # ------------------------------------------------------------------

    async def _grok(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> GenerationResult:
        if not self._grok_key:
            raise RuntimeError("XAI_API_KEY not set")
        return await self._compat_call(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://api.x.ai/v1", api_key=self._grok_key, provider="xai",
        )

    async def _grok_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> AsyncIterator[StreamChunk]:
        if not self._grok_key:
            raise RuntimeError("XAI_API_KEY not set")
        async for chunk in self._compat_stream(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://api.x.ai/v1", api_key=self._grok_key, provider="xai",
        ):
            yield chunk

    # ------------------------------------------------------------------
    # Cohere  (api.cohere.com — v2 chat endpoint)
    # ------------------------------------------------------------------

    async def _cohere(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> GenerationResult:
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install httpx")

        if not self._cohere_key:
            raise RuntimeError("COHERE_API_KEY not set")

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.cohere.com/v2/chat",
                headers={
                    "Authorization": f"Bearer {self._cohere_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "messages": messages, "max_tokens": max_tokens},
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()

        msg = data.get("message") or {}
        content_blocks = msg.get("content") or []
        text = next((b["text"] for b in content_blocks if b.get("type") == "text"), "")
        usage_raw = (data.get("usage") or {}).get("tokens") or {}
        usage = {
            "input_tokens": usage_raw.get("input_tokens", 0),
            "output_tokens": usage_raw.get("output_tokens", 0),
        }
        return GenerationResult(text=text, model=model, provider="cohere", usage=usage)

    async def _cohere_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> AsyncIterator[StreamChunk]:
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install httpx")

        if not self._cohere_key:
            raise RuntimeError("COHERE_API_KEY not set")

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        usage: dict[str, int] = {}
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                "https://api.cohere.com/v2/chat",
                headers={
                    "Authorization": f"Bearer {self._cohere_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "messages": messages, "max_tokens": max_tokens, "stream": True},
                timeout=60.0,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):].strip()
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    event_type = event.get("type", "")
                    if event_type == "content-delta":
                        delta = (event.get("delta") or {})
                        text = delta.get("text") or (delta.get("message") or {}).get("content", "")
                        if text:
                            yield StreamChunk(text=text, model=model, provider="cohere")
                    elif event_type == "message-end":
                        delta = event.get("delta") or {}
                        u = (delta.get("usage") or {}).get("tokens") or {}
                        usage = {
                            "input_tokens": u.get("input_tokens", 0),
                            "output_tokens": u.get("output_tokens", 0),
                        }

        yield StreamChunk(done=True, model=model, provider="cohere", usage=usage)

    # ------------------------------------------------------------------
    # Moonshot AI / Kimi  (api.moonshot.cn — OpenAI-compat)
    # ------------------------------------------------------------------

    async def _moonshot(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> GenerationResult:
        if not self._moonshot_key:
            raise RuntimeError("MOONSHOT_API_KEY not set")
        return await self._compat_call(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://api.moonshot.cn/v1", api_key=self._moonshot_key, provider="moonshot",
        )

    async def _moonshot_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> AsyncIterator[StreamChunk]:
        if not self._moonshot_key:
            raise RuntimeError("MOONSHOT_API_KEY not set")
        async for chunk in self._compat_stream(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://api.moonshot.cn/v1", api_key=self._moonshot_key, provider="moonshot",
        ):
            yield chunk

    # ------------------------------------------------------------------
    # Zhipu AI GLM  (open.bigmodel.cn — OpenAI-compat)
    # ------------------------------------------------------------------

    async def _glm(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> GenerationResult:
        if not self._glm_key:
            raise RuntimeError("ZHIPUAI_API_KEY not set")
        return await self._compat_call(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://open.bigmodel.cn/api/paas/v4", api_key=self._glm_key, provider="zhipu",
        )

    async def _glm_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> AsyncIterator[StreamChunk]:
        if not self._glm_key:
            raise RuntimeError("ZHIPUAI_API_KEY not set")
        async for chunk in self._compat_stream(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://open.bigmodel.cn/api/paas/v4", api_key=self._glm_key, provider="zhipu",
        ):
            yield chunk

    # ------------------------------------------------------------------
    # Alibaba Qwen / DashScope  (dashscope.aliyuncs.com — OpenAI-compat)
    # ------------------------------------------------------------------

    async def _qwen(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> GenerationResult:
        if not self._qwen_key:
            raise RuntimeError("DASHSCOPE_API_KEY not set")
        return await self._compat_call(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=self._qwen_key, provider="qwen",
        )

    async def _qwen_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> AsyncIterator[StreamChunk]:
        if not self._qwen_key:
            raise RuntimeError("DASHSCOPE_API_KEY not set")
        async for chunk in self._compat_stream(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=self._qwen_key, provider="qwen",
        ):
            yield chunk

    # ------------------------------------------------------------------
    # Baidu ERNIE / Qianfan  (qianfan.baidubce.com — OpenAI-compat v2)
    # ------------------------------------------------------------------

    async def _ernie(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> GenerationResult:
        if not self._ernie_key:
            raise RuntimeError("QIANFAN_API_KEY not set")
        return await self._compat_call(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://qianfan.baidubce.com/v2",
            api_key=self._ernie_key, provider="ernie",
        )

    async def _ernie_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> AsyncIterator[StreamChunk]:
        if not self._ernie_key:
            raise RuntimeError("QIANFAN_API_KEY not set")
        async for chunk in self._compat_stream(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://qianfan.baidubce.com/v2",
            api_key=self._ernie_key, provider="ernie",
        ):
            yield chunk

    # ------------------------------------------------------------------
    # ByteDance Doubao / Ark  (ark.cn-beijing.volces.com — OpenAI-compat)
    # ------------------------------------------------------------------

    async def _doubao(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> GenerationResult:
        if not self._doubao_key:
            raise RuntimeError("ARK_API_KEY not set")
        return await self._compat_call(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=self._doubao_key, provider="doubao",
        )

    async def _doubao_stream(
        self, model: str, *, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> AsyncIterator[StreamChunk]:
        if not self._doubao_key:
            raise RuntimeError("ARK_API_KEY not set")
        async for chunk in self._compat_stream(
            model, prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=self._doubao_key, provider="doubao",
        ):
            yield chunk

    # ------------------------------------------------------------------
    # Phase 4: runtime configuration helpers
    # ------------------------------------------------------------------

    def set_channel_override(self, channel_id: str, model: str) -> None:
        """Pin *channel_id* to always use *model* (e.g. for a fast Telegram bot)."""
        self._channel_overrides[channel_id] = model
        logger.info("model.channel_override_set channel=%s model=%s", channel_id, model)

    def clear_channel_override(self, channel_id: str) -> None:
        """Remove a channel-level model override."""
        self._channel_overrides.pop(channel_id, None)

    @property
    def channel_overrides(self) -> dict[str, str]:
        return dict(self._channel_overrides)


# ---------------------------------------------------------------------------
# Phase 4: complexity detection helper
# ---------------------------------------------------------------------------

def _detect_complexity(prompt: str) -> str:
    """Heuristically classify a prompt's complexity to pick the right model tier.

    Priority order:
    1. Keyword signals → complex_reasoning (keywords trump length)
    2. Long prompt (≥200 words) → complex_reasoning
    3. Short prompt (≤20 words, no keywords) → cheap_inference
    4. Anything else → general

    Returns one of: "complex_reasoning", "general", "cheap_inference"
    """
    prompt_lower = prompt.lower()
    words = prompt_lower.split()
    word_count = len(words)

    # Keyword scan first — short but complex queries ("explain quantum entanglement")
    # should still get the heavy model
    for kw in _COMPLEX_KEYWORDS:
        if kw in prompt_lower:
            return "complex_reasoning"

    if word_count >= _COMPLEX_WORD_THRESHOLD:
        return "complex_reasoning"

    if word_count <= _SHORT_WORD_THRESHOLD:
        return "cheap_inference"

    return "general"


# Module-level singleton
model_router = ModelRouter()

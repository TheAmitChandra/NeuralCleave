"""Tests for ModelRouter's `thinking` (normalized reasoning-effort) wiring
in _call(), _compat_call(), and generate() — P7, 2026-08-17 gap analysis.

See test_models_thinking.py for the underlying resolve_thinking_params()
mapping tested in isolation; these tests cover the router-level wiring.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from neuralcleave.models.router import (
    CLAUDE_OPUS,
    GROK_3,
    MISTRAL_LARGE,
    OPENROUTER_DEFAULT,
    GenerationResult,
    ModelRouter,
)


class TestCallThinkingClaude:
    @pytest.mark.asyncio
    async def test_thinking_high_resolves_to_extended_thinking_and_budget(self):
        router = ModelRouter(anthropic_api_key="k")
        result = GenerationResult(text="ok", model=CLAUDE_OPUS, provider="anthropic")
        with patch.object(router, "_claude", new=AsyncMock(return_value=result)) as m:
            await router._call(
                CLAUDE_OPUS, prompt="hi", system=None, max_tokens=10, temperature=0.5,
                thinking="high",
            )
        assert m.call_args[1]["extended_thinking"] is True
        assert m.call_args[1]["thinking_budget_tokens"] == 8192

    @pytest.mark.asyncio
    async def test_thinking_off_disables_extended_thinking(self):
        router = ModelRouter(anthropic_api_key="k")
        result = GenerationResult(text="ok", model=CLAUDE_OPUS, provider="anthropic")
        with patch.object(router, "_claude", new=AsyncMock(return_value=result)) as m:
            await router._call(
                CLAUDE_OPUS, prompt="hi", system=None, max_tokens=10, temperature=0.5,
                thinking="off",
            )
        assert m.call_args[1]["extended_thinking"] is False

    @pytest.mark.asyncio
    async def test_no_thinking_level_preserves_raw_kwargs_backward_compat(self):
        router = ModelRouter(anthropic_api_key="k")
        result = GenerationResult(text="ok", model=CLAUDE_OPUS, provider="anthropic")
        with patch.object(router, "_claude", new=AsyncMock(return_value=result)) as m:
            await router._call(
                CLAUDE_OPUS, prompt="hi", system=None, max_tokens=10, temperature=0.5,
                extended_thinking=True, thinking_budget_tokens=1234,
            )
        assert m.call_args[1]["extended_thinking"] is True
        assert m.call_args[1]["thinking_budget_tokens"] == 1234


class TestCallThinkingXai:
    @pytest.mark.asyncio
    async def test_thinking_high_resolves_to_reasoning_effort(self):
        router = ModelRouter(grok_api_key="k")
        result = GenerationResult(text="ok", model=GROK_3, provider="xai")
        with patch.object(router, "_grok", new=AsyncMock(return_value=result)) as m:
            await router._call(
                GROK_3, prompt="hi", system=None, max_tokens=10, temperature=0.5, thinking="high",
            )
        assert m.call_args[1]["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_thinking_max_collapses_to_high(self):
        router = ModelRouter(grok_api_key="k")
        result = GenerationResult(text="ok", model=GROK_3, provider="xai")
        with patch.object(router, "_grok", new=AsyncMock(return_value=result)) as m:
            await router._call(
                GROK_3, prompt="hi", system=None, max_tokens=10, temperature=0.5, thinking="max",
            )
        assert m.call_args[1]["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_thinking_off_passes_no_reasoning_effort(self):
        router = ModelRouter(grok_api_key="k")
        result = GenerationResult(text="ok", model=GROK_3, provider="xai")
        with patch.object(router, "_grok", new=AsyncMock(return_value=result)) as m:
            await router._call(
                GROK_3, prompt="hi", system=None, max_tokens=10, temperature=0.5, thinking="off",
            )
        assert m.call_args[1]["reasoning_effort"] is None

    @pytest.mark.asyncio
    async def test_no_thinking_level_passes_no_reasoning_effort(self):
        router = ModelRouter(grok_api_key="k")
        result = GenerationResult(text="ok", model=GROK_3, provider="xai")
        with patch.object(router, "_grok", new=AsyncMock(return_value=result)) as m:
            await router._call(GROK_3, prompt="hi", system=None, max_tokens=10, temperature=0.5)
        assert m.call_args[1]["reasoning_effort"] is None


class TestCallThinkingOpenRouter:
    @pytest.mark.asyncio
    async def test_thinking_medium_resolves_to_reasoning_effort(self):
        router = ModelRouter(openrouter_api_key="k")
        result = GenerationResult(text="ok", model=OPENROUTER_DEFAULT, provider="openrouter")
        with patch.object(router, "_openrouter", new=AsyncMock(return_value=result)) as m:
            await router._call(
                OPENROUTER_DEFAULT, prompt="hi", system=None, max_tokens=10, temperature=0.5,
                thinking="medium",
            )
        assert m.call_args[1]["reasoning_effort"] == "medium"


class TestCallThinkingOllama:
    """Round 4 (2026-08-21 gap analysis) P2: extends the ladder to Ollama's
    real `think` field (collapsed to a boolean — see test_models_thinking.py
    for why)."""

    @pytest.mark.asyncio
    async def test_thinking_high_resolves_to_think_true(self):
        router = ModelRouter()
        result = GenerationResult(text="ok", model="ollama/llama3.2", provider="ollama")
        with patch.object(router, "_ollama", new=AsyncMock(return_value=result)) as m:
            await router._call(
                "ollama/llama3.2", prompt="hi", system=None, max_tokens=10, temperature=0.5,
                thinking="high",
            )
        assert m.call_args[1]["think"] is True

    @pytest.mark.asyncio
    async def test_thinking_off_resolves_to_think_false(self):
        router = ModelRouter()
        result = GenerationResult(text="ok", model="ollama/llama3.2", provider="ollama")
        with patch.object(router, "_ollama", new=AsyncMock(return_value=result)) as m:
            await router._call(
                "ollama/llama3.2", prompt="hi", system=None, max_tokens=10, temperature=0.5,
                thinking="off",
            )
        assert m.call_args[1]["think"] is False

    @pytest.mark.asyncio
    async def test_no_thinking_level_passes_think_none(self):
        router = ModelRouter()
        result = GenerationResult(text="ok", model="ollama/llama3.2", provider="ollama")
        with patch.object(router, "_ollama", new=AsyncMock(return_value=result)) as m:
            await router._call(
                "ollama/llama3.2", prompt="hi", system=None, max_tokens=10, temperature=0.5,
            )
        assert m.call_args[1]["think"] is None


class TestOllamaThinkPayload:
    @pytest.mark.asyncio
    async def test_think_included_in_payload_when_set(self):
        from unittest.mock import MagicMock

        router = ModelRouter()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"response": "hi"})
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(router, "_audited_client", return_value=mock_client):
            await router._ollama("llama3.2", prompt="hi", system=None, max_tokens=10, think=True)

        payload = mock_client.post.call_args[1]["json"]
        assert payload["think"] is True

    @pytest.mark.asyncio
    async def test_think_omitted_when_none(self):
        from unittest.mock import MagicMock

        router = ModelRouter()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"response": "hi"})
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(router, "_audited_client", return_value=mock_client):
            await router._ollama("llama3.2", prompt="hi", system=None, max_tokens=10)

        payload = mock_client.post.call_args[1]["json"]
        assert "think" not in payload


class TestCallThinkingUnsupportedProvider:
    @pytest.mark.asyncio
    async def test_thinking_ignored_for_mistral_without_crashing(self):
        router = ModelRouter(mistral_api_key="k")
        result = GenerationResult(text="ok", model=MISTRAL_LARGE, provider="mistral")
        with patch.object(router, "_mistral", new=AsyncMock(return_value=result)) as m:
            await router._call(
                MISTRAL_LARGE, prompt="hi", system=None, max_tokens=10, temperature=0.5,
                thinking="high",
            )
        m.assert_called_once()
        assert "reasoning_effort" not in m.call_args[1]

    @pytest.mark.asyncio
    async def test_thinking_ignored_for_deepseek_without_crashing(self):
        """DeepSeek has no per-request reasoning-effort field (see
        models/thinking.py) — a thinking level must be silently dropped,
        never passed through as a fabricated kwarg."""
        router = ModelRouter(deepseek_api_key="k")
        result = GenerationResult(text="ok", model="deepseek-reasoner", provider="deepseek")
        with patch.object(router, "_deepseek", new=AsyncMock(return_value=result)) as m:
            await router._call(
                "deepseek-reasoner", prompt="hi", system=None, max_tokens=10, temperature=0.5,
                thinking="high",
            )
        m.assert_called_once()
        assert "thinking" not in m.call_args[1]
        assert "reasoning_effort" not in m.call_args[1]
        assert "think" not in m.call_args[1]


class TestGenerateThinkingEndToEnd:
    @pytest.mark.asyncio
    async def test_generate_thinking_flows_through_to_claude(self):
        router = ModelRouter(anthropic_api_key="k")
        result = GenerationResult(text="ok", model=CLAUDE_OPUS, provider="anthropic")
        with patch.object(router, "_claude", new=AsyncMock(return_value=result)) as m:
            await router.generate("analyze deeply", task_type="complex_reasoning", thinking="high")
        assert m.call_args[1]["extended_thinking"] is True
        assert m.call_args[1]["thinking_budget_tokens"] == 8192


class TestRouterLevelDefaultThinkingLevel:
    """Backs the /think slash command — set once, applies to every
    subsequent generate() call that doesn't pass `thinking` explicitly."""

    @pytest.mark.asyncio
    async def test_default_thinking_level_used_when_not_passed_explicitly(self):
        router = ModelRouter(anthropic_api_key="k")
        router._thinking_level = "high"
        result = GenerationResult(text="ok", model=CLAUDE_OPUS, provider="anthropic")
        with patch.object(router, "_claude", new=AsyncMock(return_value=result)) as m:
            await router.generate("analyze deeply", task_type="complex_reasoning")
        assert m.call_args[1]["extended_thinking"] is True
        assert m.call_args[1]["thinking_budget_tokens"] == 8192

    @pytest.mark.asyncio
    async def test_explicit_thinking_overrides_the_router_default(self):
        router = ModelRouter(anthropic_api_key="k")
        router._thinking_level = "low"
        result = GenerationResult(text="ok", model=CLAUDE_OPUS, provider="anthropic")
        with patch.object(router, "_claude", new=AsyncMock(return_value=result)) as m:
            await router.generate("analyze deeply", task_type="complex_reasoning", thinking="max")
        assert m.call_args[1]["thinking_budget_tokens"] == 32000

    @pytest.mark.asyncio
    async def test_no_default_and_no_explicit_thinking_is_a_no_op(self):
        router = ModelRouter(anthropic_api_key="k")
        result = GenerationResult(text="ok", model=CLAUDE_OPUS, provider="anthropic")
        with patch.object(router, "_claude", new=AsyncMock(return_value=result)) as m:
            await router.generate("hi", task_type="complex_reasoning")
        assert m.call_args[1]["extended_thinking"] is False

    def test_default_thinking_level_starts_as_none(self):
        router = ModelRouter()
        assert router._thinking_level is None


class TestCompatCallReasoningEffort:
    @pytest.mark.asyncio
    async def test_reasoning_effort_included_in_payload_when_set(self):
        from unittest.mock import MagicMock

        router = ModelRouter()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(
            return_value={"choices": [{"message": {"content": "hi"}}], "usage": {}}
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(router, "_audited_client", return_value=mock_client):
            await router._compat_call(
                "grok-3", prompt="hi", system=None, max_tokens=10, temperature=0.5,
                base_url="https://api.x.ai/v1", api_key="k", provider="xai",
                reasoning_effort="high",
            )

        payload = mock_client.post.call_args[1]["json"]
        assert payload["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_reasoning_effort_omitted_when_none(self):
        from unittest.mock import MagicMock

        router = ModelRouter()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(
            return_value={"choices": [{"message": {"content": "hi"}}], "usage": {}}
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(router, "_audited_client", return_value=mock_client):
            await router._compat_call(
                "grok-3", prompt="hi", system=None, max_tokens=10, temperature=0.5,
                base_url="https://api.x.ai/v1", api_key="k", provider="xai",
            )

        payload = mock_client.post.call_args[1]["json"]
        assert "reasoning_effort" not in payload

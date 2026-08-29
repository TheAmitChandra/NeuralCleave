"""Tests for ModelRouter.generate(model_override=...).

Added to let AgentOrchestrator.route() force a specific node's configured
model for a single call, without needing a router-wide _forced_provider
mutation (which would leak across concurrent callers) or a channel_id-based
override (which nothing in the orchestrator has a natural channel_id for).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from neuralcleave.models.router import CLAUDE_OPUS, GenerationResult, ModelRouter


@pytest.mark.asyncio
async def test_model_override_is_used_as_the_first_attempt() -> None:
    router = ModelRouter(auto_complexity=False)
    result = GenerationResult(text="ok", model="custom-model", provider="custom")
    with patch.object(router, "_call", new=AsyncMock(return_value=result)) as m:
        await router.generate("hi", model_override="custom-model")
    assert m.call_args[0][0] == "custom-model"


@pytest.mark.asyncio
async def test_model_override_falls_back_to_the_normal_chain_on_failure() -> None:
    router = ModelRouter(auto_complexity=False)
    result = GenerationResult(text="ok", model=CLAUDE_OPUS, provider="anthropic")
    calls: list[str] = []

    async def _call(model_id, **_kwargs):
        calls.append(model_id)
        if model_id == "custom-model":
            raise RuntimeError("custom model unavailable")
        return result

    with patch.object(router, "_call", new=_call):
        gen = await router.generate("hi", task_type="general", model_override="custom-model")

    assert calls[0] == "custom-model"
    assert len(calls) > 1  # fell through to the normal chain
    assert gen.model == CLAUDE_OPUS


@pytest.mark.asyncio
async def test_model_override_does_not_duplicate_a_model_already_in_the_chain() -> None:
    router = ModelRouter(auto_complexity=False)
    calls: list[str] = []

    async def _call(model_id, **_kwargs):
        calls.append(model_id)
        raise RuntimeError("boom")

    with patch.object(router, "_call", new=_call):
        with pytest.raises(RuntimeError, match="All providers exhausted"):
            await router.generate("hi", task_type="complex_reasoning", model_override=CLAUDE_OPUS)

    assert calls.count(CLAUDE_OPUS) == 1


@pytest.mark.asyncio
async def test_privacy_mode_overrides_model_override() -> None:
    """Privacy mode is a user safety setting - a node config forcing a
    cloud model must never silently bypass it."""
    router = ModelRouter(auto_complexity=False)
    router.privacy_mode = True
    result = GenerationResult(text="ok", model="ollama/llama3.2", provider="ollama")
    with patch.object(router, "_call", new=AsyncMock(return_value=result)) as m:
        await router.generate("hi", model_override=CLAUDE_OPUS)
    assert m.call_args[0][0] != CLAUDE_OPUS


@pytest.mark.asyncio
async def test_no_model_override_leaves_normal_routing_unchanged() -> None:
    router = ModelRouter(auto_complexity=False)
    result = GenerationResult(text="ok", model=CLAUDE_OPUS, provider="anthropic")
    with patch.object(router, "_call", new=AsyncMock(return_value=result)) as m:
        await router.generate("hi", task_type="complex_reasoning")
    assert m.call_args[0][0] == CLAUDE_OPUS

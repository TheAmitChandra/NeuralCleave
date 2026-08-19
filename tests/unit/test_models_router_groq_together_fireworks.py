"""Tests for the 3 providers added in the P3 gap-closing pass (round 3,
2026-08-17 analysis): Groq, Together AI, and Fireworks AI — mirrors the
conventions in test_models_router_openrouter_azure_bedrock.py, since all
three reuse _compat_call/_compat_stream the same way OpenRouter does.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.models.router import (
    _PROVIDER_TO_MODEL,
    _ROUTING,
    FIREWORKS_LLAMA_V3P1_70B,
    GROQ_LLAMA_3_3_70B,
    TOGETHER_LLAMA_3_3_70B,
    GenerationResult,
    ModelRouter,
    StreamChunk,
)


async def _collect(stream):
    return [chunk async for chunk in stream]


# ---------------------------------------------------------------------------
# Constants and routing table wiring
# ---------------------------------------------------------------------------


def test_groq_constant():
    assert GROQ_LLAMA_3_3_70B == "groq/llama-3.3-70b-versatile"


def test_together_constant():
    assert TOGETHER_LLAMA_3_3_70B == "together/meta-llama/Llama-3.3-70B-Instruct-Turbo"


def test_fireworks_constant():
    assert FIREWORKS_LLAMA_V3P1_70B == "fireworks/accounts/fireworks/models/llama-v3p1-70b-instruct"


def test_provider_to_model_groq():
    assert _PROVIDER_TO_MODEL["groq"] == GROQ_LLAMA_3_3_70B


def test_provider_to_model_together():
    assert _PROVIDER_TO_MODEL["together"] == TOGETHER_LLAMA_3_3_70B


def test_provider_to_model_fireworks():
    assert _PROVIDER_TO_MODEL["fireworks"] == FIREWORKS_LLAMA_V3P1_70B


def test_groq_reachable_via_cheap_inference_chain():
    assert GROQ_LLAMA_3_3_70B in _ROUTING["cheap_inference"]


def test_all_three_reachable_via_general_chain():
    assert GROQ_LLAMA_3_3_70B in _ROUTING["general"]
    assert TOGETHER_LLAMA_3_3_70B in _ROUTING["general"]
    assert FIREWORKS_LLAMA_V3P1_70B in _ROUTING["general"]


# ---------------------------------------------------------------------------
# Shared success/error assertions, parametrized across the 3 providers
# ---------------------------------------------------------------------------

_PROVIDERS = [
    ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "groq_api_key"),
    (
        "together", "TOGETHER_API_KEY", "https://api.together.xyz/v1",
        "meta-llama/Llama-3.3-70B-Instruct-Turbo", "together_api_key",
    ),
    (
        "fireworks", "FIREWORKS_API_KEY", "https://api.fireworks.ai/inference/v1",
        "accounts/fireworks/models/llama-v3p1-70b-instruct", "fireworks_api_key",
    ),
]


class TestCompatProviders:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider,env_var,base_url,model,key_kwarg", _PROVIDERS)
    async def test_raises_if_no_api_key(self, provider, env_var, base_url, model, key_kwarg):
        router = ModelRouter(**{key_kwarg: ""})
        method = getattr(router, f"_{provider}")
        with pytest.raises(RuntimeError, match=env_var):
            await method(model, prompt="hi", system=None, max_tokens=100, temperature=0.5)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider,env_var,base_url,model,key_kwarg", _PROVIDERS)
    async def test_stream_raises_if_no_api_key(self, provider, env_var, base_url, model, key_kwarg):
        router = ModelRouter(**{key_kwarg: ""})
        method = getattr(router, f"_{provider}_stream")
        with pytest.raises(RuntimeError, match=env_var):
            async for _ in method(model, prompt="hi", system=None, max_tokens=100, temperature=0.5):
                pass

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider,env_var,base_url,model,key_kwarg", _PROVIDERS)
    async def test_success_posts_to_correct_base_url(self, provider, env_var, base_url, model, key_kwarg):
        router = ModelRouter(**{key_kwarg: "test-key"})
        method = getattr(router, f"_{provider}")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": f"hi from {provider}"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await method(model, prompt="hi", system=None, max_tokens=100, temperature=0.5)

        assert result.text == f"hi from {provider}"
        assert result.provider == provider
        assert result.usage == {"input_tokens": 5, "output_tokens": 3}
        call_args = mock_client.post.call_args
        assert call_args.args[0] == f"{base_url}/chat/completions"
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider,env_var,base_url,model,key_kwarg", _PROVIDERS)
    async def test_stream_yields_text_chunks(self, provider, env_var, base_url, model, key_kwarg):
        router = ModelRouter(**{key_kwarg: "test-key"})
        method = getattr(router, f"_{provider}_stream")

        lines = [
            f"data: {json.dumps({'choices': [{'delta': {'content': 'Hel'}}]})}",
            f"data: {json.dumps({'choices': [{'delta': {'content': 'lo'}}], 'usage': {'prompt_tokens': 4, 'completion_tokens': 2}})}",
            "data: [DONE]",
        ]

        async def _aiter_lines():
            for line in lines:
                yield line

        mock_stream_resp = MagicMock()
        mock_stream_resp.raise_for_status = MagicMock()
        mock_stream_resp.aiter_lines = _aiter_lines

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _collect(
                method(model, prompt="hi", system=None, max_tokens=100, temperature=0.5)
            )

        text_chunks = [c.text for c in result if c.text]
        assert text_chunks == ["Hel", "lo"]
        assert result[-1].done is True
        assert result[-1].usage == {"input_tokens": 4, "output_tokens": 2}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider,env_var,base_url,model,key_kwarg", _PROVIDERS)
    async def test_call_dispatch_strips_namespace_prefix(self, provider, env_var, base_url, model, key_kwarg):
        router = ModelRouter(**{key_kwarg: "k"})
        with patch.object(
            router, f"_{provider}",
            new=AsyncMock(return_value=GenerationResult(text="ok", model="m", provider=provider)),
        ) as mock_call:
            await router._call(
                f"{provider}/{model}", prompt="hi", system=None, max_tokens=100, temperature=0.5,
            )
        mock_call.assert_awaited_once()
        assert mock_call.call_args.args[0] == model

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider,env_var,base_url,model,key_kwarg", _PROVIDERS)
    async def test_call_stream_dispatch_strips_namespace_prefix(self, provider, env_var, base_url, model, key_kwarg):
        router = ModelRouter(**{key_kwarg: "k"})

        async def _fake_stream(*_a, **_k):
            yield StreamChunk(done=True, model="m", provider=provider)

        with patch.object(router, f"_{provider}_stream", side_effect=_fake_stream) as mock_call:
            await _collect(
                router._call_stream(
                    f"{provider}/{model}", prompt="hi", system=None, max_tokens=100, temperature=0.5,
                )
            )
        assert mock_call.call_args.args[0] == model

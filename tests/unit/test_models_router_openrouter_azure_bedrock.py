"""Tests for the 3 providers added in the P4 gap-closing pass: OpenRouter,
Azure OpenAI, and Amazon Bedrock — mirrors the conventions in
test_models_router_new_providers.py (the earlier 8-provider batch) and
test_models_router_streaming.py (sys.modules patching for SDK clients).
"""

from __future__ import annotations

import builtins
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.models.router import (
    _PROVIDER_TO_MODEL,
    _ROUTING,
    AZURE_GPT4O,
    BEDROCK_CLAUDE,
    OPENROUTER_DEFAULT,
    GenerationResult,
    ModelRouter,
    StreamChunk,
)

# ---------------------------------------------------------------------------
# Shared async helpers
# ---------------------------------------------------------------------------


class _AsyncIter:
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self._items:
            yield item


async def _collect(stream):
    return [chunk async for chunk in stream]


# ---------------------------------------------------------------------------
# Constants and routing table wiring
# ---------------------------------------------------------------------------


def test_openrouter_default_constant():
    assert OPENROUTER_DEFAULT == "openrouter/openai/gpt-4o-mini"


def test_azure_gpt4o_constant():
    assert AZURE_GPT4O == "azure/gpt-4o"


def test_bedrock_claude_constant():
    assert BEDROCK_CLAUDE == "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"


def test_provider_to_model_openrouter():
    assert _PROVIDER_TO_MODEL["openrouter"] == OPENROUTER_DEFAULT


def test_provider_to_model_azure():
    assert _PROVIDER_TO_MODEL["azure"] == AZURE_GPT4O


def test_provider_to_model_bedrock():
    assert _PROVIDER_TO_MODEL["bedrock"] == BEDROCK_CLAUDE


def test_openrouter_reachable_via_general_chain():
    assert OPENROUTER_DEFAULT in _ROUTING["general"]


def test_azure_reachable_via_code_generation_chain():
    assert AZURE_GPT4O in _ROUTING["code_generation"]


def test_bedrock_reachable_via_complex_reasoning_chain():
    assert BEDROCK_CLAUDE in _ROUTING["complex_reasoning"]


# ---------------------------------------------------------------------------
# OpenRouter — reuses _compat_call/_compat_stream, same shape as Mistral/Grok
# ---------------------------------------------------------------------------


class TestOpenRouter:
    @pytest.mark.asyncio
    async def test_raises_if_no_api_key(self):
        router = ModelRouter(openrouter_api_key="")
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            await router._openrouter("openai/gpt-4o-mini", prompt="hi", system=None, max_tokens=100, temperature=0.5)

    @pytest.mark.asyncio
    async def test_success_posts_to_openrouter_base_url(self):
        router = ModelRouter(openrouter_api_key="or-test-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "hi from openrouter"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await router._openrouter(
                "openai/gpt-4o-mini", prompt="hi", system=None, max_tokens=100, temperature=0.5,
            )

        assert result.text == "hi from openrouter"
        assert result.provider == "openrouter"
        assert result.usage == {"input_tokens": 5, "output_tokens": 3}
        call_args = mock_client.post.call_args
        assert call_args.args[0] == "https://openrouter.ai/api/v1/chat/completions"
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer or-test-key"

    @pytest.mark.asyncio
    async def test_stream_raises_if_no_api_key(self):
        router = ModelRouter(openrouter_api_key="")
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            async for _ in router._openrouter_stream(
                "openai/gpt-4o-mini", prompt="hi", system=None, max_tokens=100, temperature=0.5,
            ):
                pass

    @pytest.mark.asyncio
    async def test_stream_yields_text_chunks(self):
        router = ModelRouter(openrouter_api_key="or-test-key")

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
                router._openrouter_stream(
                    "openai/gpt-4o-mini", prompt="hi", system=None, max_tokens=100, temperature=0.5,
                )
            )

        text_chunks = [c.text for c in result if c.text]
        assert text_chunks == ["Hel", "lo"]
        assert result[-1].done is True
        assert result[-1].usage == {"input_tokens": 4, "output_tokens": 2}

    @pytest.mark.asyncio
    async def test_call_dispatch_strips_namespace_prefix(self):
        router = ModelRouter(openrouter_api_key="k")
        with patch.object(
            router, "_openrouter", new=AsyncMock(return_value=GenerationResult(text="ok", model="m", provider="openrouter"))
        ) as mock_call:
            await router._call(
                "openrouter/openai/gpt-4o-mini", prompt="hi", system=None, max_tokens=100, temperature=0.5,
            )
        mock_call.assert_awaited_once()
        assert mock_call.call_args.args[0] == "openai/gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_call_stream_dispatch_strips_namespace_prefix(self):
        router = ModelRouter(openrouter_api_key="k")

        async def _fake_stream(*_a, **_k):
            yield StreamChunk(done=True, model="m", provider="openrouter")

        with patch.object(router, "_openrouter_stream", side_effect=_fake_stream) as mock_call:
            await _collect(
                router._call_stream(
                    "openrouter/openai/gpt-4o-mini", prompt="hi", system=None, max_tokens=100, temperature=0.5,
                )
            )
        assert mock_call.call_args.args[0] == "openai/gpt-4o-mini"


# ---------------------------------------------------------------------------
# Azure OpenAI — AsyncAzureOpenAI, model id is the deployment name
# ---------------------------------------------------------------------------


def _mock_openai_module() -> MagicMock:
    """A minimal fake 'openai' module — lets tests that only care about
    ModelRouter's own logic (config checks, dispatch) run regardless of
    whether the real openai package happens to be installed, instead of
    silently depending on incidental environment state."""
    mock_openai = MagicMock()
    mock_openai.AsyncAzureOpenAI = MagicMock(return_value=MagicMock())
    return mock_openai


class TestAzure:
    @pytest.mark.asyncio
    async def test_raises_if_no_api_key(self):
        router = ModelRouter(azure_api_key="", azure_endpoint="https://x.openai.azure.com")
        with patch.dict("sys.modules", {"openai": _mock_openai_module()}):
            with pytest.raises(RuntimeError, match="AZURE_OPENAI"):
                await router._azure("gpt-4o", prompt="hi", system=None, max_tokens=100, temperature=0.5)

    @pytest.mark.asyncio
    async def test_raises_if_no_endpoint(self):
        router = ModelRouter(azure_api_key="az-key", azure_endpoint="")
        with patch.dict("sys.modules", {"openai": _mock_openai_module()}):
            with pytest.raises(RuntimeError, match="AZURE_OPENAI"):
                await router._azure("gpt-4o", prompt="hi", system=None, max_tokens=100, temperature=0.5)

    @pytest.mark.asyncio
    async def test_success_returns_generation_result(self):
        router = ModelRouter(azure_api_key="az-key", azure_endpoint="https://my-resource.openai.azure.com")

        mock_message = MagicMock()
        mock_message.content = "hi from azure"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 7
        mock_usage.completion_tokens = 3
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_openai = MagicMock()
        mock_openai.AsyncAzureOpenAI = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = await router._azure("gpt-4o", prompt="hi", system=None, max_tokens=100, temperature=0.5)

        assert result.text == "hi from azure"
        assert result.provider == "azure"
        assert result.model == "azure/gpt-4o"
        assert result.usage == {"input_tokens": 7, "output_tokens": 3}
        mock_openai.AsyncAzureOpenAI.assert_called_once_with(
            api_key="az-key", azure_endpoint="https://my-resource.openai.azure.com", api_version="2024-10-21",
        )

    @pytest.mark.asyncio
    async def test_stream_raises_if_not_configured(self):
        router = ModelRouter(azure_api_key="", azure_endpoint="")
        with patch.dict("sys.modules", {"openai": _mock_openai_module()}):
            with pytest.raises(RuntimeError, match="AZURE_OPENAI"):
                async for _ in router._azure_stream(
                    "gpt-4o", prompt="hi", system=None, max_tokens=100, temperature=0.5
                ):
                    pass

    @pytest.mark.asyncio
    async def test_stream_yields_text_chunks(self):
        router = ModelRouter(azure_api_key="az-key", azure_endpoint="https://x.openai.azure.com")

        def _delta_chunk(text):
            delta = MagicMock()
            delta.content = text
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            chunk.usage = None
            return chunk

        usage = MagicMock()
        usage.prompt_tokens = 6
        usage.completion_tokens = 2
        done_chunk = MagicMock()
        done_chunk.choices = []
        done_chunk.usage = usage

        chunks = [_delta_chunk("Hel"), _delta_chunk("lo"), done_chunk]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_AsyncIter(chunks))

        mock_openai = MagicMock()
        mock_openai.AsyncAzureOpenAI = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = await _collect(
                router._azure_stream("gpt-4o", prompt="hi", system=None, max_tokens=100, temperature=0.5)
            )

        text_chunks = [c.text for c in result if c.text]
        assert text_chunks == ["Hel", "lo"]
        assert result[-1].done is True
        assert result[-1].usage == {"input_tokens": 6, "output_tokens": 2}

    @pytest.mark.asyncio
    async def test_call_dispatch_strips_namespace_prefix(self):
        router = ModelRouter(azure_api_key="k", azure_endpoint="https://x.openai.azure.com")
        with patch.object(
            router, "_azure", new=AsyncMock(return_value=GenerationResult(text="ok", model="m", provider="azure"))
        ) as mock_call:
            await router._call("azure/gpt-4o", prompt="hi", system=None, max_tokens=100, temperature=0.5)
        assert mock_call.call_args.args[0] == "gpt-4o"


# ---------------------------------------------------------------------------
# Amazon Bedrock — boto3 Converse API via asyncio.to_thread
# ---------------------------------------------------------------------------


def _fake_import_with_boto3(fake_boto3):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "boto3":
            return fake_boto3
        return real_import(name, *args, **kwargs)

    return fake_import


class TestBedrock:
    @pytest.mark.asyncio
    async def test_raises_if_boto3_not_installed(self):
        router = ModelRouter()
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "boto3":
                raise ImportError("No module named 'boto3'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(RuntimeError, match="pip install boto3"):
                await router._bedrock(
                    "anthropic.claude-3-5-sonnet-20241022-v2:0",
                    prompt="hi", system=None, max_tokens=100, temperature=0.5,
                )

    @pytest.mark.asyncio
    async def test_success_returns_generation_result(self):
        router = ModelRouter(bedrock_region="us-west-2")

        mock_bedrock_client = MagicMock()
        mock_bedrock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "hi from bedrock"}]}},
            "usage": {"inputTokens": 8, "outputTokens": 4},
        }
        fake_boto3 = MagicMock()
        fake_boto3.client = MagicMock(return_value=mock_bedrock_client)

        with patch("builtins.__import__", side_effect=_fake_import_with_boto3(fake_boto3)):
            result = await router._bedrock(
                "anthropic.claude-3-5-sonnet-20241022-v2:0",
                prompt="hi", system="be nice", max_tokens=100, temperature=0.5,
            )

        assert result.text == "hi from bedrock"
        assert result.provider == "bedrock"
        assert result.model == "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
        assert result.usage == {"input_tokens": 8, "output_tokens": 4}
        fake_boto3.client.assert_called_once_with("bedrock-runtime", region_name="us-west-2")
        converse_kwargs = mock_bedrock_client.converse.call_args.kwargs
        assert converse_kwargs["system"] == [{"text": "be nice"}]

    @pytest.mark.asyncio
    async def test_call_runs_in_a_thread_not_the_event_loop(self):
        """Regression guard: boto3 is synchronous — calling it directly on the
        event loop would block every other in-flight request."""
        router = ModelRouter()
        mock_bedrock_client = MagicMock()
        mock_bedrock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "usage": {},
        }
        fake_boto3 = MagicMock()
        fake_boto3.client = MagicMock(return_value=mock_bedrock_client)

        with (
            patch("builtins.__import__", side_effect=_fake_import_with_boto3(fake_boto3)),
            patch("asyncio.to_thread", new=AsyncMock(wraps=lambda fn: fn())) as mock_to_thread,
        ):
            await router._bedrock("m", prompt="hi", system=None, max_tokens=100, temperature=0.5)

        mock_to_thread.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stream_yields_single_text_chunk_then_done(self):
        """Bedrock streaming is a pseudo-stream (documented limitation) — the
        full text arrives as one chunk, not token-by-token."""
        router = ModelRouter()
        mock_bedrock_client = MagicMock()
        mock_bedrock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "full reply"}]}},
            "usage": {"inputTokens": 1, "outputTokens": 2},
        }
        fake_boto3 = MagicMock()
        fake_boto3.client = MagicMock(return_value=mock_bedrock_client)

        with patch("builtins.__import__", side_effect=_fake_import_with_boto3(fake_boto3)):
            result = await _collect(
                router._bedrock_stream("m", prompt="hi", system=None, max_tokens=100, temperature=0.5)
            )

        text_chunks = [c.text for c in result if c.text]
        assert text_chunks == ["full reply"]
        assert result[-1].done is True
        assert result[-1].usage == {"input_tokens": 1, "output_tokens": 2}

    @pytest.mark.asyncio
    async def test_call_dispatch_strips_namespace_prefix(self):
        router = ModelRouter()
        with patch.object(
            router, "_bedrock", new=AsyncMock(return_value=GenerationResult(text="ok", model="m", provider="bedrock"))
        ) as mock_call:
            await router._call(
                "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
                prompt="hi", system=None, max_tokens=100, temperature=0.5,
            )
        assert mock_call.call_args.args[0] == "anthropic.claude-3-5-sonnet-20241022-v2:0"

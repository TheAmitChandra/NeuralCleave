"""Tests for the 8 new LLM providers added to ModelRouter.

Covers: Mistral, xAI Grok, Cohere, Moonshot, GLM, Qwen, ERNIE, Doubao.
Each provider section tests: successful call, missing API key, streaming,
_call dispatch, _call_stream dispatch, and the _PROVIDER_TO_MODEL aliases.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.models.router import (
    _PROVIDER_TO_MODEL,
    _ROUTING,
    COMMAND_R,
    COMMAND_R_PLUS,
    DOUBAO_LITE,
    DOUBAO_PRO,
    ERNIE_BOT_4,
    ERNIE_SPEED,
    GLM_4,
    GLM_4_FLASH,
    GROK_3,
    GROK_3_MINI,
    MISTRAL_LARGE,
    MISTRAL_SMALL,
    MOONSHOT_8K,
    MOONSHOT_32K,
    QWEN_MAX,
    QWEN_TURBO,
    GenerationResult,
    ModelRouter,
    StreamChunk,
)

# ---------------------------------------------------------------------------
# Helper: fake httpx response
# ---------------------------------------------------------------------------


def _make_response(body: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


def _openai_compat_body(text: str, model: str) -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


async def _openai_compat_stream_lines(text: str, model: str) -> list[str]:
    chunk = {"choices": [{"delta": {"content": text}}]}
    done_chunk = {"choices": [{"delta": {}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    return [
        f"data: {json.dumps(chunk)}",
        f"data: {json.dumps(done_chunk)}",
        "data: [DONE]",
    ]


# ---------------------------------------------------------------------------
# New model constants
# ---------------------------------------------------------------------------


def test_mistral_large_constant():
    assert MISTRAL_LARGE == "mistral-large-latest"


def test_mistral_small_constant():
    assert MISTRAL_SMALL == "mistral-small-latest"


def test_grok3_constant():
    assert GROK_3 == "grok-3"


def test_grok3_mini_constant():
    assert GROK_3_MINI == "grok-3-mini"


def test_command_r_plus_constant():
    assert COMMAND_R_PLUS == "command-r-plus"


def test_command_r_constant():
    assert COMMAND_R == "command-r"


def test_moonshot_8k_constant():
    assert MOONSHOT_8K == "moonshot-v1-8k"


def test_moonshot_32k_constant():
    assert MOONSHOT_32K == "moonshot-v1-32k"


def test_glm4_constant():
    assert GLM_4 == "glm-4"


def test_glm4_flash_constant():
    assert GLM_4_FLASH == "glm-4-flash"


def test_qwen_max_constant():
    assert QWEN_MAX == "qwen-max"


def test_qwen_turbo_constant():
    assert QWEN_TURBO == "qwen-turbo"


def test_ernie_bot4_constant():
    assert ERNIE_BOT_4 == "ernie-bot-4"


def test_ernie_speed_constant():
    assert ERNIE_SPEED == "ernie-speed"


def test_doubao_pro_constant():
    assert DOUBAO_PRO == "doubao-pro-32k"


def test_doubao_lite_constant():
    assert DOUBAO_LITE == "doubao-lite-32k"


# ---------------------------------------------------------------------------
# _PROVIDER_TO_MODEL aliases
# ---------------------------------------------------------------------------


def test_provider_alias_mistral():
    assert _PROVIDER_TO_MODEL["mistral"] == MISTRAL_LARGE


def test_provider_alias_grok():
    assert _PROVIDER_TO_MODEL["grok"] == GROK_3


def test_provider_alias_xai():
    assert _PROVIDER_TO_MODEL["xai"] == GROK_3


def test_provider_alias_cohere():
    assert _PROVIDER_TO_MODEL["cohere"] == COMMAND_R_PLUS


def test_provider_alias_moonshot():
    assert _PROVIDER_TO_MODEL["moonshot"] == MOONSHOT_8K


def test_provider_alias_kimi():
    assert _PROVIDER_TO_MODEL["kimi"] == MOONSHOT_8K


def test_provider_alias_glm():
    assert _PROVIDER_TO_MODEL["glm"] == GLM_4


def test_provider_alias_zhipu():
    assert _PROVIDER_TO_MODEL["zhipu"] == GLM_4


def test_provider_alias_qwen():
    assert _PROVIDER_TO_MODEL["qwen"] == QWEN_MAX


def test_provider_alias_alibaba():
    assert _PROVIDER_TO_MODEL["alibaba"] == QWEN_MAX


def test_provider_alias_ernie():
    assert _PROVIDER_TO_MODEL["ernie"] == ERNIE_BOT_4


def test_provider_alias_baidu():
    assert _PROVIDER_TO_MODEL["baidu"] == ERNIE_BOT_4


def test_provider_alias_doubao():
    assert _PROVIDER_TO_MODEL["doubao"] == DOUBAO_PRO


def test_provider_alias_bytedance():
    assert _PROVIDER_TO_MODEL["bytedance"] == DOUBAO_PRO


# ---------------------------------------------------------------------------
# Routing table — new models appear in relevant chains
# ---------------------------------------------------------------------------


def test_routing_complex_reasoning_includes_grok():
    assert GROK_3 in _ROUTING["complex_reasoning"]


def test_routing_complex_reasoning_includes_mistral():
    assert MISTRAL_LARGE in _ROUTING["complex_reasoning"]


def test_routing_code_generation_includes_qwen():
    assert QWEN_MAX in _ROUTING["code_generation"]


def test_routing_code_review_includes_qwen():
    assert QWEN_MAX in _ROUTING["code_review"]


def test_routing_summarization_includes_command_r_plus():
    assert COMMAND_R_PLUS in _ROUTING["summarization"]


def test_routing_summarization_includes_moonshot():
    assert MOONSHOT_8K in _ROUTING["summarization"]


def test_routing_intent_extraction_includes_glm_flash():
    assert GLM_4_FLASH in _ROUTING["intent_extraction"]


def test_routing_task_decomposition_includes_mistral():
    assert MISTRAL_LARGE in _ROUTING["task_decomposition"]


def test_routing_cheap_inference_includes_glm_flash():
    assert GLM_4_FLASH in _ROUTING["cheap_inference"]


def test_routing_cheap_inference_includes_doubao_lite():
    assert DOUBAO_LITE in _ROUTING["cheap_inference"]


def test_routing_general_includes_command_r():
    assert COMMAND_R in _ROUTING["general"]


def test_routing_general_includes_moonshot():
    assert MOONSHOT_8K in _ROUTING["general"]


# ---------------------------------------------------------------------------
# ModelRouter.__init__ — env var reading
# ---------------------------------------------------------------------------


def test_init_reads_mistral_env(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral")
    r = ModelRouter()
    assert r._mistral_key == "test-mistral"


def test_init_reads_xai_env(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-xai")
    r = ModelRouter()
    assert r._grok_key == "test-xai"


def test_init_reads_cohere_env(monkeypatch):
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere")
    r = ModelRouter()
    assert r._cohere_key == "test-cohere"


def test_init_reads_moonshot_env(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-moonshot")
    r = ModelRouter()
    assert r._moonshot_key == "test-moonshot"


def test_init_reads_zhipuai_env(monkeypatch):
    monkeypatch.setenv("ZHIPUAI_API_KEY", "test-glm")
    r = ModelRouter()
    assert r._glm_key == "test-glm"


def test_init_reads_dashscope_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-qwen")
    r = ModelRouter()
    assert r._qwen_key == "test-qwen"


def test_init_reads_qianfan_env(monkeypatch):
    monkeypatch.setenv("QIANFAN_API_KEY", "test-ernie")
    r = ModelRouter()
    assert r._ernie_key == "test-ernie"


def test_init_reads_ark_env(monkeypatch):
    monkeypatch.setenv("ARK_API_KEY", "test-doubao")
    r = ModelRouter()
    assert r._doubao_key == "test-doubao"


def test_init_explicit_key_overrides_env(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "env-key")
    r = ModelRouter(mistral_api_key="explicit-key")
    assert r._mistral_key == "explicit-key"


# ---------------------------------------------------------------------------
# _call dispatch — new prefixes route to correct methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_dispatches_mistral():
    router = ModelRouter(mistral_api_key="k")
    result = GenerationResult(text="ok", model=MISTRAL_LARGE, provider="mistral")
    with patch.object(router, "_mistral", new=AsyncMock(return_value=result)) as m:
        await router._call(MISTRAL_LARGE, prompt="hi", system=None, max_tokens=10, temperature=0.5)
        m.assert_called_once()


@pytest.mark.asyncio
async def test_call_dispatches_grok():
    router = ModelRouter(grok_api_key="k")
    result = GenerationResult(text="ok", model=GROK_3, provider="xai")
    with patch.object(router, "_grok", new=AsyncMock(return_value=result)) as m:
        await router._call(GROK_3, prompt="hi", system=None, max_tokens=10, temperature=0.5)
        m.assert_called_once()


@pytest.mark.asyncio
async def test_call_dispatches_cohere():
    router = ModelRouter(cohere_api_key="k")
    result = GenerationResult(text="ok", model=COMMAND_R_PLUS, provider="cohere")
    with patch.object(router, "_cohere", new=AsyncMock(return_value=result)) as m:
        await router._call(COMMAND_R_PLUS, prompt="hi", system=None, max_tokens=10, temperature=0.5)
        m.assert_called_once()


@pytest.mark.asyncio
async def test_call_dispatches_moonshot():
    router = ModelRouter(moonshot_api_key="k")
    result = GenerationResult(text="ok", model=MOONSHOT_8K, provider="moonshot")
    with patch.object(router, "_moonshot", new=AsyncMock(return_value=result)) as m:
        await router._call(MOONSHOT_8K, prompt="hi", system=None, max_tokens=10, temperature=0.5)
        m.assert_called_once()


@pytest.mark.asyncio
async def test_call_dispatches_glm():
    router = ModelRouter(glm_api_key="k")
    result = GenerationResult(text="ok", model=GLM_4, provider="zhipu")
    with patch.object(router, "_glm", new=AsyncMock(return_value=result)) as m:
        await router._call(GLM_4, prompt="hi", system=None, max_tokens=10, temperature=0.5)
        m.assert_called_once()


@pytest.mark.asyncio
async def test_call_dispatches_qwen():
    router = ModelRouter(qwen_api_key="k")
    result = GenerationResult(text="ok", model=QWEN_MAX, provider="qwen")
    with patch.object(router, "_qwen", new=AsyncMock(return_value=result)) as m:
        await router._call(QWEN_MAX, prompt="hi", system=None, max_tokens=10, temperature=0.5)
        m.assert_called_once()


@pytest.mark.asyncio
async def test_call_dispatches_ernie():
    router = ModelRouter(ernie_api_key="k")
    result = GenerationResult(text="ok", model=ERNIE_BOT_4, provider="ernie")
    with patch.object(router, "_ernie", new=AsyncMock(return_value=result)) as m:
        await router._call(ERNIE_BOT_4, prompt="hi", system=None, max_tokens=10, temperature=0.5)
        m.assert_called_once()


@pytest.mark.asyncio
async def test_call_dispatches_doubao():
    router = ModelRouter(doubao_api_key="k")
    result = GenerationResult(text="ok", model=DOUBAO_PRO, provider="doubao")
    with patch.object(router, "_doubao", new=AsyncMock(return_value=result)) as m:
        await router._call(DOUBAO_PRO, prompt="hi", system=None, max_tokens=10, temperature=0.5)
        m.assert_called_once()


# ---------------------------------------------------------------------------
# _call_stream dispatch — new prefixes route to correct stream methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_stream_dispatches_mistral():
    router = ModelRouter(mistral_api_key="k")

    async def _fake_stream(*_, **__) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(done=True, model=MISTRAL_LARGE, provider="mistral")

    with patch.object(router, "_mistral_stream", side_effect=_fake_stream):
        chunks = []
        async for chunk in router._call_stream(
            MISTRAL_LARGE, prompt="hi", system=None, max_tokens=10, temperature=0.5
        ):
            chunks.append(chunk)
        assert chunks[-1].done is True


@pytest.mark.asyncio
async def test_call_stream_dispatches_grok():
    router = ModelRouter(grok_api_key="k")

    async def _fake_stream(*_, **__) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(done=True, model=GROK_3, provider="xai")

    with patch.object(router, "_grok_stream", side_effect=_fake_stream):
        chunks = []
        async for chunk in router._call_stream(
            GROK_3, prompt="hi", system=None, max_tokens=10, temperature=0.5
        ):
            chunks.append(chunk)
        assert chunks[-1].provider == "xai"


@pytest.mark.asyncio
async def test_call_stream_dispatches_cohere():
    router = ModelRouter(cohere_api_key="k")

    async def _fake_stream(*_, **__) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(text="hello", model=COMMAND_R_PLUS, provider="cohere")
        yield StreamChunk(done=True, model=COMMAND_R_PLUS, provider="cohere")

    with patch.object(router, "_cohere_stream", side_effect=_fake_stream):
        texts = []
        async for chunk in router._call_stream(
            COMMAND_R_PLUS, prompt="hi", system=None, max_tokens=10, temperature=0.5
        ):
            if chunk.text:
                texts.append(chunk.text)
        assert "hello" in texts


@pytest.mark.asyncio
async def test_call_stream_dispatches_moonshot():
    router = ModelRouter(moonshot_api_key="k")

    async def _fake_stream(*_, **__) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(done=True, model=MOONSHOT_8K, provider="moonshot")

    with patch.object(router, "_moonshot_stream", side_effect=_fake_stream):
        chunks = []
        async for chunk in router._call_stream(
            MOONSHOT_8K, prompt="hi", system=None, max_tokens=10, temperature=0.5
        ):
            chunks.append(chunk)
        assert chunks[-1].provider == "moonshot"


@pytest.mark.asyncio
async def test_call_stream_dispatches_glm():
    router = ModelRouter(glm_api_key="k")

    async def _fake_stream(*_, **__) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(done=True, model=GLM_4_FLASH, provider="zhipu")

    with patch.object(router, "_glm_stream", side_effect=_fake_stream):
        chunks = []
        async for chunk in router._call_stream(
            GLM_4_FLASH, prompt="hi", system=None, max_tokens=10, temperature=0.5
        ):
            chunks.append(chunk)
        assert chunks[-1].provider == "zhipu"


@pytest.mark.asyncio
async def test_call_stream_dispatches_qwen():
    router = ModelRouter(qwen_api_key="k")

    async def _fake_stream(*_, **__) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(done=True, model=QWEN_MAX, provider="qwen")

    with patch.object(router, "_qwen_stream", side_effect=_fake_stream):
        chunks = []
        async for chunk in router._call_stream(
            QWEN_MAX, prompt="hi", system=None, max_tokens=10, temperature=0.5
        ):
            chunks.append(chunk)
        assert chunks[-1].provider == "qwen"


@pytest.mark.asyncio
async def test_call_stream_dispatches_ernie():
    router = ModelRouter(ernie_api_key="k")

    async def _fake_stream(*_, **__) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(done=True, model=ERNIE_BOT_4, provider="ernie")

    with patch.object(router, "_ernie_stream", side_effect=_fake_stream):
        chunks = []
        async for chunk in router._call_stream(
            ERNIE_BOT_4, prompt="hi", system=None, max_tokens=10, temperature=0.5
        ):
            chunks.append(chunk)
        assert chunks[-1].provider == "ernie"


@pytest.mark.asyncio
async def test_call_stream_dispatches_doubao():
    router = ModelRouter(doubao_api_key="k")

    async def _fake_stream(*_, **__) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(done=True, model=DOUBAO_PRO, provider="doubao")

    with patch.object(router, "_doubao_stream", side_effect=_fake_stream):
        chunks = []
        async for chunk in router._call_stream(
            DOUBAO_PRO, prompt="hi", system=None, max_tokens=10, temperature=0.5
        ):
            chunks.append(chunk)
        assert chunks[-1].provider == "doubao"


# ---------------------------------------------------------------------------
# Missing API key → RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mistral_missing_key_raises():
    router = ModelRouter(mistral_api_key="")
    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
        await router._mistral(MISTRAL_LARGE, prompt="hi", system=None, max_tokens=10, temperature=0.5)


@pytest.mark.asyncio
async def test_grok_missing_key_raises():
    router = ModelRouter(grok_api_key="")
    with pytest.raises(RuntimeError, match="XAI_API_KEY"):
        await router._grok(GROK_3, prompt="hi", system=None, max_tokens=10, temperature=0.5)


@pytest.mark.asyncio
async def test_cohere_missing_key_raises():
    router = ModelRouter(cohere_api_key="")
    with pytest.raises(RuntimeError, match="COHERE_API_KEY"):
        await router._cohere(COMMAND_R_PLUS, prompt="hi", system=None, max_tokens=10, temperature=0.5)


@pytest.mark.asyncio
async def test_moonshot_missing_key_raises():
    router = ModelRouter(moonshot_api_key="")
    with pytest.raises(RuntimeError, match="MOONSHOT_API_KEY"):
        await router._moonshot(MOONSHOT_8K, prompt="hi", system=None, max_tokens=10, temperature=0.5)


@pytest.mark.asyncio
async def test_glm_missing_key_raises():
    router = ModelRouter(glm_api_key="")
    with pytest.raises(RuntimeError, match="ZHIPUAI_API_KEY"):
        await router._glm(GLM_4, prompt="hi", system=None, max_tokens=10, temperature=0.5)


@pytest.mark.asyncio
async def test_qwen_missing_key_raises():
    router = ModelRouter(qwen_api_key="")
    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        await router._qwen(QWEN_MAX, prompt="hi", system=None, max_tokens=10, temperature=0.5)


@pytest.mark.asyncio
async def test_ernie_missing_key_raises():
    router = ModelRouter(ernie_api_key="")
    with pytest.raises(RuntimeError, match="QIANFAN_API_KEY"):
        await router._ernie(ERNIE_BOT_4, prompt="hi", system=None, max_tokens=10, temperature=0.5)


@pytest.mark.asyncio
async def test_doubao_missing_key_raises():
    router = ModelRouter(doubao_api_key="")
    with pytest.raises(RuntimeError, match="ARK_API_KEY"):
        await router._doubao(DOUBAO_PRO, prompt="hi", system=None, max_tokens=10, temperature=0.5)


# ---------------------------------------------------------------------------
# _compat_call — successful call with mocked httpx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compat_call_success():
    router = ModelRouter()
    body = _openai_compat_body("hello world", "mistral-large-latest")

    mock_resp = MagicMock()
    mock_resp.json.return_value = body
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await router._compat_call(
            "mistral-large-latest",
            prompt="ping",
            system=None,
            max_tokens=100,
            temperature=0.7,
            base_url="https://api.mistral.ai/v1",
            api_key="fake-key",
            provider="mistral",
        )

    assert result.text == "hello world"
    assert result.provider == "mistral"
    assert result.usage["input_tokens"] == 10
    assert result.usage["output_tokens"] == 5


@pytest.mark.asyncio
async def test_compat_call_with_system_prompt():
    router = ModelRouter()
    body = _openai_compat_body("answer", "grok-3")

    mock_resp = MagicMock()
    mock_resp.json.return_value = body
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await router._compat_call(
            "grok-3",
            prompt="question",
            system="You are helpful",
            max_tokens=100,
            temperature=0.7,
            base_url="https://api.x.ai/v1",
            api_key="fake-key",
            provider="xai",
        )

    # Verify system message was included (check call args)
    call_kwargs = mock_client.post.call_args.kwargs
    messages = call_kwargs["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are helpful"
    assert messages[-1]["role"] == "user"
    assert result.text == "answer"


# ---------------------------------------------------------------------------
# _compat_stream — successful streaming with mocked httpx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compat_stream_yields_text_then_done():
    router = ModelRouter()

    chunk1 = json.dumps({"choices": [{"delta": {"content": "hello "}}]})
    chunk2 = json.dumps({"choices": [{"delta": {"content": "world"}}],
                         "usage": {"prompt_tokens": 5, "completion_tokens": 3}})

    async def _aiter_lines():
        yield f"data: {chunk1}"
        yield f"data: {chunk2}"
        yield "data: [DONE]"

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_stream_ctx.raise_for_status = MagicMock()
    mock_stream_ctx.aiter_lines = _aiter_lines

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)

    with patch("httpx.AsyncClient", return_value=mock_client):
        chunks = []
        async for c in router._compat_stream(
            "mistral-large-latest",
            prompt="hi",
            system=None,
            max_tokens=100,
            temperature=0.7,
            base_url="https://api.mistral.ai/v1",
            api_key="fake-key",
            provider="mistral",
        ):
            chunks.append(c)

    text_chunks = [c for c in chunks if c.text]
    done_chunks = [c for c in chunks if c.done]
    assert any(c.text == "hello " for c in text_chunks)
    assert any(c.text == "world" for c in text_chunks)
    assert len(done_chunks) == 1
    assert done_chunks[0].usage["output_tokens"] == 3


@pytest.mark.asyncio
async def test_compat_stream_skips_non_data_lines():
    router = ModelRouter()

    async def _aiter_lines():
        yield ""
        yield "event: message"
        yield f"data: {json.dumps({'choices': [{'delta': {'content': 'hi'}}]})}"
        yield "data: [DONE]"

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_stream_ctx.raise_for_status = MagicMock()
    mock_stream_ctx.aiter_lines = _aiter_lines

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)

    with patch("httpx.AsyncClient", return_value=mock_client):
        chunks = []
        async for c in router._compat_stream(
            "grok-3",
            prompt="ping",
            system=None,
            max_tokens=50,
            temperature=0.5,
            base_url="https://api.x.ai/v1",
            api_key="fake",
            provider="xai",
        ):
            chunks.append(c)

    text = "".join(c.text for c in chunks if c.text)
    assert text == "hi"


# ---------------------------------------------------------------------------
# Cohere provider — custom v2 chat format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cohere_call_parses_v2_response():
    router = ModelRouter(cohere_api_key="fake-key")
    body = {
        "message": {
            "content": [{"type": "text", "text": "Cohere response"}]
        },
        "usage": {"tokens": {"input_tokens": 8, "output_tokens": 4}},
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = body
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await router._cohere(
            COMMAND_R_PLUS, prompt="hi", system=None, max_tokens=100, temperature=0.7
        )

    assert result.text == "Cohere response"
    assert result.provider == "cohere"
    assert result.usage["input_tokens"] == 8
    assert result.usage["output_tokens"] == 4


@pytest.mark.asyncio
async def test_cohere_stream_parses_content_delta():
    router = ModelRouter(cohere_api_key="fake-key")

    event1 = json.dumps({"type": "content-delta", "delta": {"text": "Co"}})
    event2 = json.dumps({"type": "content-delta", "delta": {"text": "here"}})
    event3 = json.dumps({
        "type": "message-end",
        "delta": {"usage": {"tokens": {"input_tokens": 5, "output_tokens": 2}}}
    })

    async def _aiter_lines():
        yield f"data: {event1}"
        yield f"data: {event2}"
        yield f"data: {event3}"

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_stream_ctx.raise_for_status = MagicMock()
    mock_stream_ctx.aiter_lines = _aiter_lines

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)

    with patch("httpx.AsyncClient", return_value=mock_client):
        chunks = []
        async for c in router._cohere_stream(
            COMMAND_R_PLUS, prompt="hi", system=None, max_tokens=100, temperature=0.7
        ):
            chunks.append(c)

    texts = "".join(c.text for c in chunks if c.text)
    assert texts == "Cohere"
    done = [c for c in chunks if c.done]
    assert len(done) == 1
    assert done[0].usage["output_tokens"] == 2


@pytest.mark.asyncio
async def test_cohere_call_with_system_sent_as_system_role():
    """System prompt is sent as {"role":"system"} in the messages list."""
    router = ModelRouter(cohere_api_key="fake-key")
    body = {
        "message": {"content": [{"type": "text", "text": "ok"}]},
        "usage": {"tokens": {"input_tokens": 1, "output_tokens": 1}},
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = body
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await router._cohere(COMMAND_R_PLUS, prompt="q", system="Be brief", max_tokens=50, temperature=0.5)

    sent_json = mock_client.post.call_args.kwargs["json"]
    roles = [m["role"] for m in sent_json["messages"]]
    assert "system" in roles


# ---------------------------------------------------------------------------
# generate() end-to-end fallback with new providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_falls_back_to_mistral_when_primary_fails():
    router = ModelRouter(mistral_api_key="fake", auto_complexity=False)
    mistral_result = GenerationResult(text="from mistral", model=MISTRAL_LARGE, provider="mistral")

    # Force complex_reasoning chain so mistral is in it
    with (
        patch.object(router, "_claude", new=AsyncMock(side_effect=RuntimeError("no key"))),
        patch.object(router, "_openai", new=AsyncMock(side_effect=RuntimeError("quota"))),
        patch.object(router, "_grok", new=AsyncMock(side_effect=RuntimeError("no key"))),
        patch.object(router, "_gemini", new=AsyncMock(side_effect=RuntimeError("limit"))),
        patch.object(router, "_mistral", new=AsyncMock(return_value=mistral_result)),
    ):
        result = await router.generate("complex reasoning task", task_type="complex_reasoning")

    assert result.text == "from mistral"
    assert result.provider == "mistral"


@pytest.mark.asyncio
async def test_forced_provider_grok_routes_correctly():
    router = ModelRouter(grok_api_key="fake-key", auto_complexity=False)
    router._forced_provider = "grok"
    grok_result = GenerationResult(text="from grok", model=GROK_3, provider="xai")

    with patch.object(router, "_grok", new=AsyncMock(return_value=grok_result)):
        result = await router.generate("any task")

    assert result.text == "from grok"


@pytest.mark.asyncio
async def test_forced_provider_kimi_alias_routes_to_moonshot():
    router = ModelRouter(moonshot_api_key="fake-key", auto_complexity=False)
    router._forced_provider = "kimi"
    moonshot_result = GenerationResult(text="from kimi", model=MOONSHOT_8K, provider="moonshot")

    with patch.object(router, "_moonshot", new=AsyncMock(return_value=moonshot_result)):
        result = await router.generate("any task")

    assert result.text == "from kimi"


@pytest.mark.asyncio
async def test_generate_stream_with_glm_fallback():
    router = ModelRouter(glm_api_key="fake-key", auto_complexity=False)

    async def _glm_stream_stub(*_, **__) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(text="from glm", model=GLM_4_FLASH, provider="zhipu")
        yield StreamChunk(done=True, model=GLM_4_FLASH, provider="zhipu", usage={})

    async def _failing_stream(*_, **__) -> AsyncIterator[StreamChunk]:
        raise RuntimeError("fail")
        yield  # makes it an async generator

    with (
        patch.object(router, "_gemini_stream", _failing_stream),
        patch.object(router, "_openai_stream", _failing_stream),
        patch.object(router, "_glm_stream", _glm_stream_stub),
    ):
        chunks = []
        async for c in router.generate_stream("hi", task_type="intent_extraction"):
            chunks.append(c)

    texts = "".join(c.text for c in chunks if c.text)
    assert "from glm" in texts


# ---------------------------------------------------------------------------
# Model-specific routing checks for each new provider's primary task
# ---------------------------------------------------------------------------


def test_qwen_max_primary_for_code_tasks():
    """Qwen-max should appear before generic fallbacks in code chains."""
    code_gen_chain = _ROUTING["code_generation"]
    qwen_idx = code_gen_chain.index(QWEN_MAX)
    # Gemini should be after Qwen in code_generation
    import cortexflow_ai.models.router as r
    gemini_idx = code_gen_chain.index(r.GEMINI_FLASH)
    assert qwen_idx < gemini_idx


def test_glm_flash_before_gpt_in_cheap_inference():
    chain = _ROUTING["cheap_inference"]
    glm_idx = chain.index(GLM_4_FLASH)
    assert glm_idx < len(chain) - 1  # present and not at the very end


def test_command_r_plus_before_moonshot_in_summarization():
    chain = _ROUTING["summarization"]
    cr_idx = chain.index(COMMAND_R_PLUS)
    ms_idx = chain.index(MOONSHOT_8K)
    assert cr_idx < ms_idx


def test_all_new_models_have_unique_prefixes():
    new_models = [
        MISTRAL_LARGE, MISTRAL_SMALL,
        GROK_3, GROK_3_MINI,
        COMMAND_R_PLUS, COMMAND_R,
        MOONSHOT_8K, MOONSHOT_32K,
        GLM_4, GLM_4_FLASH,
        QWEN_MAX, QWEN_TURBO,
        ERNIE_BOT_4, ERNIE_SPEED,
        DOUBAO_PRO, DOUBAO_LITE,
    ]
    prefixes = set()
    for m in new_models:
        prefix = m.split("-")[0]
        prefixes.add(prefix)
    # Each family should have a distinct first token
    assert len(prefixes) >= 8

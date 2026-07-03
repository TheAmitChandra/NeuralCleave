"""Unit tests for ModelRouter.generate_stream() and the per-provider streams."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.models.router import GEMINI_FLASH, ModelRouter, StreamChunk

# ---------------------------------------------------------------------------
# Shared async helpers
# ---------------------------------------------------------------------------


class _AsyncCM:
    """Minimal async context manager wrapping a fixed value."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc):
        return False


class _AsyncIter:
    """Minimal async-iterable wrapping a fixed list of items."""

    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self._items:
            yield item


async def _collect(stream) -> list[StreamChunk]:
    return [chunk async for chunk in stream]


# ---------------------------------------------------------------------------
# generate_stream() — routing/fallback behaviour, provider-agnostic
# ---------------------------------------------------------------------------


def _fake_stream(chunks: list[StreamChunk]):
    async def _gen(*_args, **_kwargs):
        for c in chunks:
            yield c
    return _gen


@pytest.mark.asyncio
async def test_generate_stream_yields_chunks_from_primary_provider() -> None:
    router = ModelRouter(auto_complexity=False)
    chunks = [
        StreamChunk(text="Hel", model=GEMINI_FLASH, provider="google"),
        StreamChunk(text="lo", model=GEMINI_FLASH, provider="google"),
        StreamChunk(done=True, model=GEMINI_FLASH, provider="google", usage={"output_tokens": 2}),
    ]
    with patch.object(router, "_gemini_stream", new=_fake_stream(chunks)):
        result = await _collect(router.generate_stream("hi"))

    assert [c.text for c in result] == ["Hel", "lo", ""]
    assert result[-1].done is True
    assert result[-1].usage == {"output_tokens": 2}


@pytest.mark.asyncio
async def test_generate_stream_falls_back_when_primary_fails_before_yielding() -> None:
    router = ModelRouter(auto_complexity=False)

    async def _failing(*_args, **_kwargs):
        raise RuntimeError("quota exceeded")
        yield  # pragma: no cover - makes this an async generator function

    ollama_chunks = [StreamChunk(text="ok", model="llama3.2", provider="ollama")]
    with (
        patch.object(router, "_gemini_stream", new=_failing),
        patch.object(router, "_ollama_stream", new=_fake_stream(ollama_chunks)),
    ):
        result = await _collect(router.generate_stream("hi"))

    assert [c.text for c in result] == ["ok"]
    assert result[0].provider == "ollama"


@pytest.mark.asyncio
async def test_generate_stream_does_not_fall_back_after_partial_output() -> None:
    """Once content has reached the caller, a mid-stream failure must not
    silently retry on the next provider — that would duplicate or
    contradict text already shown. It should surface as an error chunk."""
    router = ModelRouter(auto_complexity=False)

    async def _partial_then_fail(*_args, **_kwargs):
        yield StreamChunk(text="partial", model=GEMINI_FLASH, provider="google")
        raise RuntimeError("connection dropped")

    with (
        patch.object(router, "_gemini_stream", new=_partial_then_fail),
        patch.object(router, "_ollama_stream", new=_fake_stream([StreamChunk(text="should not run")])),
    ):
        result = await _collect(router.generate_stream("hi"))

    assert result[0].text == "partial"
    assert result[1].done is True
    assert result[1].error == "connection dropped"
    assert len(result) == 2  # the ollama fallback never ran


@pytest.mark.asyncio
async def test_generate_stream_raises_when_all_providers_fail() -> None:
    router = ModelRouter(auto_complexity=False)

    async def _failing(*_args, **_kwargs):
        raise RuntimeError("down")
        yield  # pragma: no cover

    with (
        patch.object(router, "_gemini_stream", new=_failing),
        patch.object(router, "_ollama_stream", new=_failing),
    ):
        with pytest.raises(RuntimeError, match="All providers exhausted"):
            await _collect(router.generate_stream("hi"))


# ---------------------------------------------------------------------------
# _ollama_stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_stream_yields_incremental_text_then_done_with_usage() -> None:
    router = ModelRouter()
    lines = [
        json.dumps({"response": "Hel", "done": False}),
        json.dumps({"response": "lo", "done": False}),
        json.dumps({"response": "", "done": True, "prompt_eval_count": 5, "eval_count": 2}),
    ]

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    async def aiter_lines():
        for line in lines:
            yield line

    mock_resp.aiter_lines = aiter_lines

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=_AsyncCM(mock_resp))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await _collect(router._ollama_stream("llama3.2", prompt="hi", system=None, max_tokens=100))

    assert [c.text for c in result] == ["Hel", "lo", ""]
    assert result[-1].done is True
    assert result[-1].usage == {"input_tokens": 5, "output_tokens": 2}


@pytest.mark.asyncio
async def test_ollama_stream_raises_if_httpx_not_installed() -> None:
    router = ModelRouter()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="pip install httpx"):
            await _collect(router._ollama_stream("llama3.2", prompt="hi", system=None, max_tokens=100))


# ---------------------------------------------------------------------------
# _gemini_stream
# ---------------------------------------------------------------------------


def _genai_sys_modules(mock_genai) -> dict:
    mock_google = MagicMock()
    mock_google.generativeai = mock_genai
    return {"google": mock_google, "google.generativeai": mock_genai}


@pytest.mark.asyncio
async def test_gemini_stream_yields_text_chunks_then_done_with_usage() -> None:
    router = ModelRouter(gemini_api_key="sk-test")

    chunk1 = MagicMock(text="Hel")
    chunk1.usage_metadata = None
    usage_meta = MagicMock()
    usage_meta.prompt_token_count = 7
    usage_meta.candidates_token_count = 3
    chunk2 = MagicMock(text="lo")
    chunk2.usage_metadata = usage_meta

    mock_genai = MagicMock()
    mock_genai.configure = MagicMock()
    mock_genai.GenerationConfig = MagicMock()
    mock_gmodel = MagicMock()
    mock_gmodel.generate_content_async = AsyncMock(return_value=_AsyncIter([chunk1, chunk2]))
    mock_genai.GenerativeModel = MagicMock(return_value=mock_gmodel)

    with patch.dict("sys.modules", _genai_sys_modules(mock_genai)):
        result = await _collect(
            router._gemini_stream(GEMINI_FLASH, prompt="hi", system=None, max_tokens=100)
        )

    assert [c.text for c in result] == ["Hel", "lo", ""]
    assert result[-1].done is True
    assert result[-1].usage == {"input_tokens": 7, "output_tokens": 3}
    call_kwargs = mock_gmodel.generate_content_async.call_args[1]
    assert call_kwargs["stream"] is True


@pytest.mark.asyncio
async def test_gemini_stream_raises_if_no_api_key() -> None:
    import os
    mock_genai = MagicMock()
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
        router = ModelRouter(gemini_api_key="")
        with patch.dict("sys.modules", _genai_sys_modules(mock_genai)):
            with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
                await _collect(router._gemini_stream(GEMINI_FLASH, prompt="hi", system=None, max_tokens=100))


# ---------------------------------------------------------------------------
# _claude_stream
# ---------------------------------------------------------------------------


class _ClaudeStreamCM:
    def __init__(self, texts: list[str], final_message):
        self._texts = texts
        self._final_message = final_message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def _gen():
            for t in self._texts:
                yield t
        return _gen()

    async def get_final_message(self):
        return self._final_message


@pytest.mark.asyncio
async def test_claude_stream_yields_text_then_done_with_usage() -> None:
    router = ModelRouter(anthropic_api_key="sk-test")

    final_message = MagicMock()
    final_message.usage.input_tokens = 11
    final_message.usage.output_tokens = 22

    client = MagicMock()
    client.messages.stream = MagicMock(return_value=_ClaudeStreamCM(["Hel", "lo"], final_message))

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic = MagicMock(return_value=client)

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        result = await _collect(
            router._claude_stream("claude-opus-4-8", prompt="hi", system=None, max_tokens=100, temperature=0.5)
        )

    assert [c.text for c in result] == ["Hel", "lo", ""]
    assert result[-1].done is True
    assert result[-1].usage == {"input_tokens": 11, "output_tokens": 22}


@pytest.mark.asyncio
async def test_claude_stream_raises_if_no_api_key() -> None:
    router = ModelRouter(anthropic_api_key="")
    mock_anthropic = MagicMock()

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            await _collect(
                router._claude_stream("claude-opus-4-8", prompt="hi", system=None, max_tokens=100, temperature=0.5)
            )


# ---------------------------------------------------------------------------
# _deepseek_stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deepseek_stream_parses_sse_lines_into_chunks() -> None:
    router = ModelRouter(deepseek_api_key="sk-test")

    sse_lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "Hel"}}]}),
        "data: " + json.dumps({"choices": [{"delta": {"content": "lo"}}]}),
        "data: " + json.dumps({"choices": [{"delta": {}}], "usage": {"prompt_tokens": 4, "completion_tokens": 2}}),
        "data: [DONE]",
    ]

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    async def aiter_lines():
        for line in sse_lines:
            yield line

    mock_resp.aiter_lines = aiter_lines

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=_AsyncCM(mock_resp))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await _collect(
            router._deepseek_stream(
                "deepseek-coder", prompt="hi", system=None, max_tokens=100, temperature=0.0
            )
        )

    assert [c.text for c in result] == ["Hel", "lo", ""]
    assert result[-1].done is True
    assert result[-1].usage == {"input_tokens": 4, "output_tokens": 2}


@pytest.mark.asyncio
async def test_deepseek_stream_raises_if_no_api_key() -> None:
    router = ModelRouter(deepseek_api_key="")
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        await _collect(
            router._deepseek_stream(
                "deepseek-coder", prompt="hi", system=None, max_tokens=100, temperature=0.0
            )
        )


# ---------------------------------------------------------------------------
# _openai_stream
# ---------------------------------------------------------------------------


def _make_openai_chunk(text: str | None, usage=None):
    chunk = MagicMock()
    if text is None:
        chunk.choices = []
    else:
        delta = MagicMock()
        delta.content = text
        choice = MagicMock()
        choice.delta = delta
        chunk.choices = [choice]
    chunk.usage = usage
    return chunk


@pytest.mark.asyncio
async def test_openai_stream_yields_text_then_done_with_usage() -> None:
    router = ModelRouter(openai_api_key="sk-test")

    usage = MagicMock()
    usage.prompt_tokens = 9
    usage.completion_tokens = 4

    chunks = [
        _make_openai_chunk("Hel"),
        _make_openai_chunk("lo"),
        _make_openai_chunk(None, usage=usage),
    ]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_AsyncIter(chunks))

    mock_openai = MagicMock()
    mock_openai.AsyncOpenAI = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"openai": mock_openai}):
        result = await _collect(
            router._openai_stream("gpt-4o", prompt="hi", system=None, max_tokens=100, temperature=0.5)
        )

    assert [c.text for c in result] == ["Hel", "lo", ""]
    assert result[-1].done is True
    assert result[-1].usage == {"input_tokens": 9, "output_tokens": 4}


@pytest.mark.asyncio
async def test_openai_stream_raises_if_no_api_key() -> None:
    router = ModelRouter(openai_api_key="")
    mock_openai = MagicMock()

    with patch.dict("sys.modules", {"openai": mock_openai}):
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            await _collect(
                router._openai_stream("gpt-4o", prompt="hi", system=None, max_tokens=100, temperature=0.5)
            )

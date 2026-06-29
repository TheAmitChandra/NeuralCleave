"""Unit tests for CognitivePipeline.run_stream()."""

from __future__ import annotations

import time

import pytest

from cortexflow_ai.agent.pipeline import CognitivePipeline, PipelineStreamChunk
from cortexflow_ai.channels.base import InboundMessage
from cortexflow_ai.memory.retrieval import RetrievalContext
from cortexflow_ai.models.router import StreamChunk

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class FakeStreamingRouter:
    """Router whose generate_stream() yields a fixed sequence of chunks,
    branching on task_type the same way test_agent_pipeline.py's FakeRouter
    does for generate()."""

    def __init__(self, intent: str = "chat", text_chunks: list[str] | None = None):
        self._intent = intent
        self._text_chunks = text_chunks if text_chunks is not None else ["Hel", "lo"]
        self.calls: list[dict] = []

    async def generate(self, prompt, *, task_type="general", **_kwargs):
        # Used only for intent extraction in the streaming path.
        from cortexflow_ai.models.router import GenerationResult
        self.calls.append({"task_type": task_type, "prompt": prompt})
        return GenerationResult(text=self._intent, model="gemini-2.0-flash", provider="google")

    async def generate_stream(self, prompt, *, task_type="general", system=None, **_kwargs):
        self.calls.append({"task_type": task_type, "prompt": prompt, "system": system})
        for t in self._text_chunks:
            yield StreamChunk(text=t, model="gemini-2.0-flash", provider="google")
        yield StreamChunk(
            done=True, model="gemini-2.0-flash", provider="google",
            usage={"input_tokens": 5, "output_tokens": len(self._text_chunks)},
        )


class FailingMidStreamRouter(FakeStreamingRouter):
    async def generate_stream(self, prompt, *, task_type="general", system=None, **_kwargs):
        yield StreamChunk(text="partial", model="m", provider="p")
        yield StreamChunk(done=True, error="connection dropped")


class FakeMemory:
    def __init__(self):
        self.retrieve_calls: list[str] = []
        self.stored: list[dict] = []

    async def retrieve(self, query, embedding=None, *, top_k=10, **kwargs):
        self.retrieve_calls.append(query)
        return RetrievalContext(results=[], token_estimate=3)

    async def store_short_term(self, key, value):
        self.stored.append({"key": key, "value": value})


class FakeWorkspace:
    def to_system_prompt(self, agent_name: str) -> str:
        return f"You are {agent_name}."


class FakeReflection:
    def __init__(self, score: float = 88.0, raise_error: bool = False):
        self._score = score
        self._raise = raise_error
        self.called_with: tuple[str, str] | None = None

    async def reflect(self, user_message, response):
        self.called_with = (user_message, response)
        if self._raise:
            raise RuntimeError("reflection boom")
        from cortexflow_ai.reflection.engine import ReflectionResult
        return ReflectionResult(
            original_response=response,
            final_response="SHOULD NOT BE USED",
            score=self._score,
            reason="ok",
        )


class FakeSession:
    def __init__(self):
        self.turn_count = 0
        self.turns: list[tuple] = []

    def add_turn(self, role, content, *, model=None):
        self.turn_count += 1
        self.turns.append((role, content, model))

    def build_prompt(self, *, include_turns=None) -> str:
        return ""

    def clear(self):
        self.turn_count = 0
        self.turns.clear()


def make_msg(text: str = "hello there") -> InboundMessage:
    return InboundMessage(
        channel="telegram", sender_id="user-1", sender_name="Alice",
        text=text, timestamp=time.time(),
    )


def make_pipeline(router=None, memory=None, reflection=None) -> CognitivePipeline:
    return CognitivePipeline(
        router=router or FakeStreamingRouter(),
        memory=memory or FakeMemory(),
        workspace=FakeWorkspace(),
        agent_name="TestBot",
        reflection=reflection,
    )


async def _collect(stream) -> list[PipelineStreamChunk]:
    return [chunk async for chunk in stream]


# ---------------------------------------------------------------------------
# run_stream()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_stream_yields_text_chunks_in_order():
    pipeline = make_pipeline(router=FakeStreamingRouter(text_chunks=["Hel", "lo"]))
    chunks = await _collect(pipeline.run_stream(make_msg(), FakeSession()))

    text_chunks = [c for c in chunks if not c.done]
    assert [c.text for c in text_chunks] == ["Hel", "lo"]


@pytest.mark.asyncio
async def test_run_stream_final_chunk_has_assembled_result():
    pipeline = make_pipeline(router=FakeStreamingRouter(text_chunks=["Hel", "lo"]))
    chunks = await _collect(pipeline.run_stream(make_msg(), FakeSession()))

    final = chunks[-1]
    assert final.done is True
    assert final.result is not None
    assert final.result.response == "Hello"
    assert final.result.model == "gemini-2.0-flash"
    assert final.result.provider == "google"
    assert final.result.usage == {"input_tokens": 5, "output_tokens": 2}


@pytest.mark.asyncio
async def test_run_stream_propagates_mid_stream_error_without_final_result():
    pipeline = make_pipeline(router=FailingMidStreamRouter())
    chunks = await _collect(pipeline.run_stream(make_msg(), FakeSession()))

    assert chunks[0].text == "partial"
    assert chunks[-1].done is True
    assert chunks[-1].error == "connection dropped"
    assert chunks[-1].result is None
    assert len(chunks) == 2


@pytest.mark.asyncio
async def test_run_stream_adds_session_turns_with_full_assembled_text():
    session = FakeSession()
    pipeline = make_pipeline(router=FakeStreamingRouter(text_chunks=["Hel", "lo"]))
    await _collect(pipeline.run_stream(make_msg("hi there"), session))

    assert session.turns[0] == ("user", "hi there", None)
    assert session.turns[1] == ("assistant", "Hello", "gemini-2.0-flash")


@pytest.mark.asyncio
async def test_run_stream_does_not_add_turns_on_mid_stream_error():
    session = FakeSession()
    pipeline = make_pipeline(router=FailingMidStreamRouter())
    await _collect(pipeline.run_stream(make_msg(), session))

    assert session.turns == []


@pytest.mark.asyncio
async def test_run_stream_persists_short_term_memory():
    memory = FakeMemory()
    pipeline = make_pipeline(router=FakeStreamingRouter(text_chunks=["ok"]), memory=memory)
    await _collect(pipeline.run_stream(make_msg(), FakeSession()))

    # store_short_term is fire-and-forget (asyncio.create_task) — give the
    # event loop a tick to run it before asserting.
    import asyncio
    await asyncio.sleep(0)
    assert len(memory.stored) == 1
    assert memory.stored[0]["value"]["assistant"] == "ok"


@pytest.mark.asyncio
async def test_run_stream_reflection_sets_quality_score_but_never_overrides_text():
    reflection = FakeReflection(score=42.0)
    pipeline = make_pipeline(
        router=FakeStreamingRouter(text_chunks=["Hel", "lo"]), reflection=reflection
    )
    chunks = await _collect(pipeline.run_stream(make_msg(), FakeSession()))

    final = chunks[-1]
    assert final.result.quality_score == 42.0
    # The streamed text the caller already saw must be preserved verbatim —
    # FakeReflection's final_response ("SHOULD NOT BE USED") must never win.
    assert final.result.response == "Hello"
    assert reflection.called_with == ("hello there", "Hello")


@pytest.mark.asyncio
async def test_run_stream_reflection_failure_leaves_quality_score_none():
    reflection = FakeReflection(raise_error=True)
    pipeline = make_pipeline(
        router=FakeStreamingRouter(text_chunks=["ok"]), reflection=reflection
    )
    chunks = await _collect(pipeline.run_stream(make_msg(), FakeSession()))

    assert chunks[-1].result.quality_score is None
    assert chunks[-1].result.response == "ok"


@pytest.mark.asyncio
async def test_run_stream_no_reflection_configured_quality_score_none():
    pipeline = make_pipeline(router=FakeStreamingRouter(text_chunks=["ok"]), reflection=None)
    chunks = await _collect(pipeline.run_stream(make_msg(), FakeSession()))

    assert chunks[-1].result.quality_score is None


@pytest.mark.asyncio
async def test_run_stream_uses_intent_extraction_and_maps_task_type():
    router = FakeStreamingRouter(intent="code", text_chunks=["x"])
    pipeline = make_pipeline(router=router)
    chunks = await _collect(pipeline.run_stream(make_msg("write me a function"), FakeSession()))

    assert chunks[-1].result.intent == "code"
    assert chunks[-1].result.task_type == "code_generation"


@pytest.mark.asyncio
async def test_run_stream_includes_retrieval_token_estimate():
    pipeline = make_pipeline(router=FakeStreamingRouter(text_chunks=["x"]))
    chunks = await _collect(pipeline.run_stream(make_msg(), FakeSession()))

    assert chunks[-1].result.retrieval_token_estimate == 3

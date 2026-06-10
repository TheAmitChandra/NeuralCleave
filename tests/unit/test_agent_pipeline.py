"""Unit tests for cortexflow.agent.pipeline — CognitivePipeline + PipelineResult."""

from __future__ import annotations

import time

import pytest

from cortexflow.agent.pipeline import (
    INTENT_TASK_MAP,
    CognitivePipeline,
    PipelineResult,
)
from cortexflow.channels.base import InboundMessage
from cortexflow.memory.retrieval import RetrievalContext
from cortexflow.models.router import GenerationResult

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class FakeRouter:
    """Router whose generate() branches on task_type.

    intent_extraction calls return the configured intent word; all other
    calls return the configured answer.
    """

    def __init__(self, intent: str = "code", answer: str = "  Final answer.  "):
        self._intent = intent
        self._answer = answer
        self.calls: list[dict] = []

    async def generate(self, prompt, *, task_type="general", system=None, max_tokens=4096, temperature=0.7):
        self.calls.append({"task_type": task_type, "prompt": prompt, "system": system})
        if task_type == "intent_extraction":
            return GenerationResult(text=self._intent, model="gemini-2.0-flash", provider="google")
        return GenerationResult(text=self._answer, model="deepseek-coder", provider="deepseek")


class FakeMemory:
    def __init__(self):
        self.retrieve_calls: list[str] = []
        self.stored: list[dict] = []

    async def retrieve(self, query, embedding=None, *, top_k=10, **kwargs):
        self.retrieve_calls.append(query)
        return RetrievalContext(results=[], token_estimate=0)

    async def store_short_term(self, key, value):
        self.stored.append({"key": key, "value": value})


class FakeMemoryWithContext(FakeMemory):
    async def retrieve(self, query, embedding=None, *, top_k=10, **kwargs):
        self.retrieve_calls.append(query)
        from cortexflow.memory.retrieval import MemoryResult

        return RetrievalContext(
            results=[MemoryResult(source="long_term", content="user likes Python", score=0.8)],
            token_estimate=5,
        )


class FakeWorkspace:
    def to_system_prompt(self, agent_name: str) -> str:
        return f"You are {agent_name}."


class FakeReflection:
    def __init__(self, final="Reflected answer.", score=88.0, raise_error=False):
        self._final = final
        self._score = score
        self._raise = raise_error
        self.called = False

    async def reflect(self, user_message, response):
        self.called = True
        if self._raise:
            raise RuntimeError("reflection boom")
        from cortexflow.reflection.engine import ReflectionResult

        return ReflectionResult(
            original_response=response,
            final_response=self._final,
            score=self._score,
            reason="ok",
        )


def make_msg(text: str = "Write a function") -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        sender_name="Alice",
        text=text,
        timestamp=time.time(),
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


def make_pipeline(router=None, memory=None, reflection=None) -> CognitivePipeline:
    return CognitivePipeline(
        router=router or FakeRouter(),
        memory=memory or FakeMemory(),
        workspace=FakeWorkspace(),
        agent_name="TestBot",
        reflection=reflection,
    )


# ---------------------------------------------------------------------------
# PipelineResult dataclass
# ---------------------------------------------------------------------------


def test_pipeline_result_defaults():
    r = PipelineResult(response="hi", model="m", provider="p", intent="chat", task_type="general")
    assert r.quality_score is None
    assert r.latency_ms == 0.0


def test_intent_task_map_has_expected_keys():
    assert INTENT_TASK_MAP["code"] == "code_generation"
    assert INTENT_TASK_MAP["debug"] == "code_review"
    assert INTENT_TASK_MAP["other"] == "general"


# ---------------------------------------------------------------------------
# run() — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_returns_pipeline_result():
    p = make_pipeline()
    result = await p.run(make_msg(), FakeSession())
    assert isinstance(result, PipelineResult)


@pytest.mark.asyncio
async def test_run_strips_response_whitespace():
    p = make_pipeline(router=FakeRouter(answer="  spaced answer  "))
    result = await p.run(make_msg(), FakeSession())
    assert result.response == "spaced answer"


@pytest.mark.asyncio
async def test_run_maps_intent_to_task_type():
    p = make_pipeline(router=FakeRouter(intent="code"))
    result = await p.run(make_msg("Write some code please"), FakeSession())
    assert result.intent == "code"
    assert result.task_type == "code_generation"


@pytest.mark.asyncio
async def test_run_records_provider_and_model():
    p = make_pipeline()
    result = await p.run(make_msg(), FakeSession())
    assert result.model == "deepseek-coder"
    assert result.provider == "deepseek"


@pytest.mark.asyncio
async def test_run_latency_is_positive():
    p = make_pipeline()
    result = await p.run(make_msg(), FakeSession())
    assert result.latency_ms >= 0.0


# ---------------------------------------------------------------------------
# Session history updates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_adds_user_and_assistant_turns():
    session = FakeSession()
    p = make_pipeline()
    await p.run(make_msg("hello there"), session)
    roles = [t[0] for t in session.turns]
    assert roles == ["user", "assistant"]


# ---------------------------------------------------------------------------
# Memory integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_calls_memory_retrieve_with_text():
    memory = FakeMemory()
    p = make_pipeline(memory=memory)
    await p.run(make_msg("find this"), session=FakeSession())
    assert "find this" in memory.retrieve_calls


@pytest.mark.asyncio
async def test_run_system_prompt_includes_memory_blocks():
    router = FakeRouter()
    p = make_pipeline(router=router, memory=FakeMemoryWithContext())
    await p.run(make_msg("question about python"), FakeSession())
    # The final generation call (not intent) should carry memory in system prompt
    gen_call = [c for c in router.calls if c["task_type"] != "intent_extraction"][0]
    assert "user likes Python" in gen_call["system"]


@pytest.mark.asyncio
async def test_run_system_prompt_includes_agent_identity():
    router = FakeRouter()
    p = make_pipeline(router=router)
    await p.run(make_msg("hi there friend"), FakeSession())
    gen_call = [c for c in router.calls if c["task_type"] != "intent_extraction"][0]
    assert "TestBot" in gen_call["system"]


# ---------------------------------------------------------------------------
# Intent extraction edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_text_intent_is_chat():
    # text < 5 chars short-circuits to "chat" without an LLM intent call
    router = FakeRouter()
    p = make_pipeline(router=router)
    result = await p.run(make_msg("hi"), FakeSession())
    assert result.intent == "chat"
    # No intent_extraction call should have happened
    assert all(c["task_type"] != "intent_extraction" for c in router.calls)


@pytest.mark.asyncio
async def test_unknown_intent_falls_back_to_other():
    router = FakeRouter(intent="banana")  # not in INTENT_TASK_MAP
    p = make_pipeline(router=router)
    result = await p.run(make_msg("some longer message here"), FakeSession())
    assert result.intent == "other"
    assert result.task_type == "general"


# ---------------------------------------------------------------------------
# Reflection wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_reflection_leaves_quality_score_none():
    p = make_pipeline()
    result = await p.run(make_msg(), FakeSession())
    assert result.quality_score is None


@pytest.mark.asyncio
async def test_reflection_sets_quality_score_and_replaces_response():
    refl = FakeReflection(final="Reflected answer.", score=91.0)
    p = make_pipeline(reflection=refl)
    result = await p.run(make_msg("a longer question for reflection"), FakeSession())
    assert refl.called is True
    assert result.quality_score == 91.0
    assert result.response == "Reflected answer."


@pytest.mark.asyncio
async def test_reflection_failure_keeps_original_response():
    refl = FakeReflection(raise_error=True)
    p = make_pipeline(router=FakeRouter(answer="original answer"), reflection=refl)
    result = await p.run(make_msg("another long question here"), FakeSession())
    assert result.response == "original answer"
    assert result.quality_score is None

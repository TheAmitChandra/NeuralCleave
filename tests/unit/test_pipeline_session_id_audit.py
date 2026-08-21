"""Tests that CognitivePipeline forwards session.session_id to ModelRouter.

ModelRouter.generate()/generate_stream() attribute outbound provider calls to
a session in the privacy audit log via a session_id kwarg (see
models/router.py's _AUDIT_SESSION_ID contextvar). These tests prove the
pipeline actually supplies the real session id at every call site instead of
letting it silently fall back to "default".
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.channels.base import InboundMessage
from neuralcleave.memory.retrieval import RetrievalContext
from neuralcleave.models.router import GenerationResult, StreamChunk
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes text back."
    parameters = {"text": {"type": "str", "description": "Input.", "required": True}}
    permissions: list[str] = []

    async def execute(self, text: str = "", **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output=text)


class _SessionCapturingTool(Tool):
    """Records the _session_id kwarg ToolRegistry.call() forwards to it."""

    name = "capture"
    description = "Captures its _session_id kwarg."
    parameters = {}
    permissions: list[str] = []

    def __init__(self) -> None:
        self.received_session_ids: list[str] = []

    async def execute(self, _session_id: str = "", **kwargs) -> ToolResult:
        self.received_session_ids.append(_session_id)
        return ToolResult(tool=self.name, output="ok")


class _RecordingRouter:
    """Router that records the session_id kwarg on every call."""

    def __init__(self, answer: str = "final answer"):
        self._answer = answer
        self.generate_session_ids: list[str | None] = []
        self.generate_stream_session_ids: list[str | None] = []

    async def generate(self, prompt, *, task_type="general", system=None, session_id=None, **_kwargs):
        self.generate_session_ids.append(session_id)
        if task_type == "intent_extraction":
            return GenerationResult(text="chat", model="m", provider="p")
        return GenerationResult(text=self._answer, model="m", provider="p")

    async def generate_stream(self, prompt, *, task_type="general", system=None, session_id=None, **_kwargs):
        self.generate_stream_session_ids.append(session_id)
        yield StreamChunk(text=self._answer, model="m", provider="p")
        yield StreamChunk(done=True, model="m", provider="p", usage={})


def _memory() -> MagicMock:
    memory = MagicMock()
    ctx = RetrievalContext(results=[], token_estimate=0)
    memory.retrieve = AsyncMock(return_value=ctx)
    memory.store_short_term = AsyncMock()
    memory.store_semantic = AsyncMock()
    return memory


def _session(session_id: str) -> MagicMock:
    session = MagicMock()
    session.session_id = session_id
    session.turn_count = 1
    session.build_prompt.return_value = ""
    return session


def _msg(text: str = "hello") -> InboundMessage:
    import time

    return InboundMessage(channel="telegram", sender_id="u", sender_name="User", text=text, timestamp=time.time())


class TestRunPassesSessionId:
    @pytest.mark.asyncio
    async def test_run_passes_session_id_to_generate(self) -> None:
        router = _RecordingRouter()
        pipeline = CognitivePipeline(
            router=router, memory=_memory(), workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
        )
        await pipeline.run(_msg(), _session("session-abc"))

        # The final (non intent-extraction) generate() call must carry the real session id.
        assert "session-abc" in router.generate_session_ids

    @pytest.mark.asyncio
    async def test_run_tool_chain_passes_session_id_to_regeneration(self) -> None:
        router = _RecordingRouter(answer='TOOL_CALL: {"name": "echo", "arguments": {"text": "hi"}}')
        registry = ToolRegistry()
        registry.register(_EchoTool())
        pipeline = CognitivePipeline(
            router=router, memory=_memory(), workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
            tool_registry=registry,
        )
        await pipeline.run(_msg(), _session("session-tools"))

        # At least the tool-chain regeneration call(s) must carry the session id.
        assert router.generate_session_ids.count("session-tools") >= 1

    @pytest.mark.asyncio
    async def test_run_tool_chain_forwards_session_id_to_the_tool_call_itself(self) -> None:
        """Round 4 (2026-08-21 gap analysis) P0: approval-gated tools
        (ShellTool, BrowserAutomationTool) need the real originating
        session_id — not just regeneration calls — to attribute a pending
        approval to the channel that triggered it."""
        router = _RecordingRouter(answer='TOOL_CALL: {"name": "capture", "arguments": {}}')
        registry = ToolRegistry()
        tool = _SessionCapturingTool()
        registry.register(tool)
        pipeline = CognitivePipeline(
            router=router, memory=_memory(), workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
            tool_registry=registry,
        )
        await pipeline.run(_msg(), _session("session-tools"))

        assert tool.received_session_ids == ["session-tools"]


class TestRunStreamPassesSessionId:
    @pytest.mark.asyncio
    async def test_run_stream_passes_session_id_to_generate_stream(self) -> None:
        router = _RecordingRouter()
        pipeline = CognitivePipeline(
            router=router, memory=_memory(), workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
        )
        session = _session("stream-session-xyz")
        async for _ in pipeline.run_stream(_msg(), session):
            pass

        assert router.generate_stream_session_ids == ["stream-session-xyz"]

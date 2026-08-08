"""Integration test: three sequential tool calls in one run() turn."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _CounterTool(Tool):
    """Returns an incrementing count each time it is called."""

    name = "counter"
    description = "Returns the invocation count."
    parameters = {}
    permissions: list[str] = []

    _n: int = 0

    async def execute(self, **kwargs) -> ToolResult:
        self._n += 1
        return ToolResult(tool=self.name, output=str(self._n))


def _make_pipeline_with_counter() -> tuple[CognitivePipeline, _CounterTool]:
    step1 = 'TOOL_CALL: {"name": "counter", "arguments": {"step": 1}}'
    step2 = 'TOOL_CALL: {"name": "counter", "arguments": {"step": 2}}'
    step3 = 'TOOL_CALL: {"name": "counter", "arguments": {"step": 3}}'
    final = "The counter reached 3."

    responses = [step1, step2, step3, final]
    call_count = [0]

    async def _gen(prompt, **kwargs):
        r = MagicMock()
        idx = min(call_count[0], len(responses) - 1)
        r.text = responses[idx]
        r.model = "m"
        r.provider = "p"
        r.usage = {}
        call_count[0] += 1
        return r

    tool = _CounterTool()
    registry = ToolRegistry()
    registry.register(tool)

    memory = MagicMock()
    ctx = MagicMock()
    ctx.to_prompt_blocks.return_value = []
    ctx.token_estimate = 0
    memory.retrieve = AsyncMock(return_value=ctx)
    memory.store_short_term = AsyncMock()

    pipeline = CognitivePipeline(
        router=MagicMock(generate=_gen),
        memory=memory,
        workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
        tool_registry=registry,
    )
    return pipeline, tool


class TestThreeStepChainIntegration:
    @pytest.mark.asyncio
    async def test_three_step_chain_result_response_is_final_text(self) -> None:
        p, _ = _make_pipeline_with_counter()
        msg = MagicMock(text="count three times")
        session = MagicMock(
            session_id="s", build_prompt=MagicMock(return_value=""), turn_count=1
        )
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(msg, session)

        assert result.response == "The counter reached 3."

    @pytest.mark.asyncio
    async def test_three_step_chain_tool_steps_equals_three(self) -> None:
        p, _ = _make_pipeline_with_counter()
        msg = MagicMock(text="count three times")
        session = MagicMock(
            session_id="s", build_prompt=MagicMock(return_value=""), turn_count=1
        )
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(msg, session)

        assert result.tool_steps == 3

    @pytest.mark.asyncio
    async def test_three_step_chain_tool_executed_three_times(self) -> None:
        p, tool = _make_pipeline_with_counter()
        msg = MagicMock(text="count")
        session = MagicMock(
            session_id="s", build_prompt=MagicMock(return_value=""), turn_count=1
        )
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            await p.run(msg, session)

        assert tool._n == 3

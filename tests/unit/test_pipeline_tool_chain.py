"""Tests for CognitivePipeline._run_tool_chain() multi-step agentic loop."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from neuralcleave.agent.pipeline import _MAX_TOOL_STEPS, CognitivePipeline
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes text back."
    parameters = {"text": {"type": "str", "description": "Input.", "required": True}}
    permissions: list[str] = []

    async def execute(self, text: str = "", **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output=text)


def _make_pipeline(responses: list[str]) -> CognitivePipeline:
    """Return a pipeline whose router yields *responses* in sequence."""
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

    registry = ToolRegistry()
    registry.register(_EchoTool())

    return CognitivePipeline(
        router=MagicMock(generate=_gen),
        memory=MagicMock(),
        workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
        tool_registry=registry,
    )


class TestRunToolChain:
    @pytest.mark.asyncio
    async def test_no_tool_call_returns_unchanged(self) -> None:
        p = _make_pipeline(["ignored"])
        text, steps = await p._run_tool_chain("plain response", "user", "sys", "general")
        assert text == "plain response"
        assert steps == 0

    @pytest.mark.asyncio
    async def test_single_tool_call_completes_in_one_step(self) -> None:
        p = _make_pipeline(["final answer"])
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "hi"}}'
        text, steps = await p._run_tool_chain(first, "user", "sys", "general")
        assert text == "final answer"
        assert steps == 1

    @pytest.mark.asyncio
    async def test_two_step_chain_executes_both_tools(self) -> None:
        p = _make_pipeline([
            'TOOL_CALL: {"name": "echo", "arguments": {"text": "step2"}}',
            "done",
        ])
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "step1"}}'
        text, steps = await p._run_tool_chain(first, "user", "sys", "general")
        assert text == "done"
        assert steps == 2

    @pytest.mark.asyncio
    async def test_loop_detection_stops_infinite_chain(self) -> None:
        repeated = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "same"}}'
        p = _make_pipeline([repeated] * (_MAX_TOOL_STEPS + 2))
        _, steps = await p._run_tool_chain(repeated, "user", "sys", "general")
        assert steps == 1  # breaks on second occurrence of the same call

    @pytest.mark.asyncio
    async def test_loop_detection_result_has_no_tool_call_marker(self) -> None:
        repeated = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "same"}}'
        p = _make_pipeline([repeated] * (_MAX_TOOL_STEPS + 2))
        text, _ = await p._run_tool_chain(repeated, "user", "sys", "general")
        assert "TOOL_CALL:" not in text

    @pytest.mark.asyncio
    async def test_max_steps_limit_is_respected(self) -> None:
        # Each re-gen emits a distinct TOOL_CALL to avoid loop detection.
        responses = [
            f'TOOL_CALL: {{"name": "echo", "arguments": {{"text": "s{i}"}}}}'
            for i in range(_MAX_TOOL_STEPS + 2)
        ]
        p = _make_pipeline(responses)
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "start"}}'
        _, steps = await p._run_tool_chain(first, "user", "sys", "general")
        assert steps == _MAX_TOOL_STEPS

    @pytest.mark.asyncio
    async def test_max_steps_result_has_no_tool_call_marker(self) -> None:
        responses = [
            f'TOOL_CALL: {{"name": "echo", "arguments": {{"text": "s{i}"}}}}'
            for i in range(_MAX_TOOL_STEPS + 2)
        ]
        p = _make_pipeline(responses)
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "start"}}'
        text, _ = await p._run_tool_chain(first, "user", "sys", "general")
        assert "TOOL_CALL:" not in text

    @pytest.mark.asyncio
    async def test_returns_zero_steps_when_registry_is_none(self) -> None:
        p = CognitivePipeline(
            router=MagicMock(),
            memory=MagicMock(),
            workspace=MagicMock(),
            tool_registry=None,
        )
        call = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "x"}}'
        text, steps = await p._run_tool_chain(call, "user", "sys", "general")
        assert steps == 0
        assert "TOOL_CALL:" in text  # returned unchanged


class TestRunToolChainCustomMaxSteps:
    @pytest.mark.asyncio
    async def test_custom_max_steps_of_one_stops_after_first_tool(self) -> None:
        # With max_tool_steps=1, even when re-gen produces another TOOL_CALL it stops.
        repeated = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "a"}}'
        second = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "b"}}'

        def _make_pipeline_custom(max_steps: int) -> CognitivePipeline:
            call_count = [0]

            async def _gen(prompt, **kwargs):
                r = MagicMock()
                r.text = second if call_count[0] == 0 else "done"
                r.model = "m"
                r.provider = "p"
                r.usage = {}
                call_count[0] += 1
                return r

            registry = ToolRegistry()

            class _E(Tool):
                name = "echo"
                description = "echo"
                parameters = {}
                permissions: list[str] = []

                async def execute(self, text: str = "", **kwargs) -> ToolResult:
                    return ToolResult(tool="echo", output=text)

            registry.register(_E())
            return CognitivePipeline(
                router=MagicMock(generate=_gen),
                memory=MagicMock(),
                workspace=MagicMock(to_system_prompt=MagicMock(return_value="s")),
                tool_registry=registry,
                max_tool_steps=max_steps,
            )

        p = _make_pipeline_custom(max_steps=1)
        _, steps = await p._run_tool_chain(repeated, "user", "sys", "general")
        assert steps == 1

    @pytest.mark.asyncio
    async def test_custom_max_steps_respected_above_default(self) -> None:
        limit = _MAX_TOOL_STEPS + 3
        call_count = [0]

        async def _gen(prompt, **kwargs):
            r = MagicMock()
            r.text = f'TOOL_CALL: {{"name": "echo", "arguments": {{"text": "s{call_count[0]}"}}}}'
            r.model = "m"
            r.provider = "p"
            r.usage = {}
            call_count[0] += 1
            return r

        class _E(Tool):
            name = "echo"
            description = "echo"
            parameters = {}
            permissions: list[str] = []

            async def execute(self, text: str = "", **kwargs) -> ToolResult:
                return ToolResult(tool="echo", output=text)

        registry = ToolRegistry()
        registry.register(_E())
        p = CognitivePipeline(
            router=MagicMock(generate=_gen),
            memory=MagicMock(),
            workspace=MagicMock(to_system_prompt=MagicMock(return_value="s")),
            tool_registry=registry,
            max_tool_steps=limit,
        )
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "start"}}'
        _, steps = await p._run_tool_chain(first, "user", "sys", "general")
        assert steps == limit

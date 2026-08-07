"""Tests that _run_tool_chain accumulates tool results in the prompt context."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _CapsTool(Tool):
    name = "caps"
    description = "Uppercases text."
    parameters = {"text": {"type": "str", "description": "Input.", "required": True}}
    permissions: list[str] = []

    async def execute(self, text: str = "", **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output=text.upper())


class TestToolChainContextAccumulation:
    @pytest.mark.asyncio
    async def test_tool_result_is_included_in_next_generation_prompt(self) -> None:
        received_prompts: list[str] = []

        async def _gen(prompt, **kwargs):
            received_prompts.append(prompt)
            r = MagicMock()
            r.text = "final answer"
            r.model = "m"
            r.provider = "p"
            r.usage = {}
            return r

        registry = ToolRegistry()
        registry.register(_CapsTool())
        p = CognitivePipeline(
            router=MagicMock(generate=_gen),
            memory=MagicMock(),
            workspace=MagicMock(to_system_prompt=MagicMock(return_value="s")),
            tool_registry=registry,
        )

        first = 'TOOL_CALL: {"name": "caps", "arguments": {"text": "hello"}}'
        await p._run_tool_chain(first, "original user prompt", "sys", "general")

        assert len(received_prompts) == 1
        # The second generate call receives the tool result block
        assert "[TOOL:caps]" in received_prompts[0]
        assert "HELLO" in received_prompts[0]

    @pytest.mark.asyncio
    async def test_context_includes_all_prior_tool_results_in_chain(self) -> None:
        received_prompts: list[str] = []
        step_responses = [
            'TOOL_CALL: {"name": "caps", "arguments": {"text": "b"}}',
            "final",
        ]
        call_count = [0]

        async def _gen(prompt, **kwargs):
            received_prompts.append(prompt)
            r = MagicMock()
            r.text = step_responses[min(call_count[0], len(step_responses) - 1)]
            r.model = "m"
            r.provider = "p"
            r.usage = {}
            call_count[0] += 1
            return r

        registry = ToolRegistry()
        registry.register(_CapsTool())
        p = CognitivePipeline(
            router=MagicMock(generate=_gen),
            memory=MagicMock(),
            workspace=MagicMock(to_system_prompt=MagicMock(return_value="s")),
            tool_registry=registry,
        )

        first = 'TOOL_CALL: {"name": "caps", "arguments": {"text": "a"}}'
        await p._run_tool_chain(first, "base", "sys", "general")

        # After two tool calls, both tool result blocks appear in the final prompt
        final_prompt = received_prompts[-1]
        assert "[TOOL:caps]" in final_prompt
        assert "A" in final_prompt  # first tool result (uppercased "a")
        assert "B" in final_prompt  # second tool result (uppercased "b")

    @pytest.mark.asyncio
    async def test_original_user_prompt_preserved_across_chain(self) -> None:
        received_prompts: list[str] = []

        async def _gen(prompt, **kwargs):
            received_prompts.append(prompt)
            r = MagicMock()
            r.text = "done"
            r.model = "m"
            r.provider = "p"
            r.usage = {}
            return r

        registry = ToolRegistry()
        registry.register(_CapsTool())
        p = CognitivePipeline(
            router=MagicMock(generate=_gen),
            memory=MagicMock(),
            workspace=MagicMock(to_system_prompt=MagicMock(return_value="s")),
            tool_registry=registry,
        )

        first = 'TOOL_CALL: {"name": "caps", "arguments": {"text": "x"}}'
        await p._run_tool_chain(first, "the original request", "sys", "general")

        assert "the original request" in received_prompts[0]

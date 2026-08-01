"""Tests for CognitivePipeline._run_tool_if_called() directly."""

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


def _make_pipeline(second_response: str = "re-generated") -> CognitivePipeline:
    async def _gen(prompt, **kwargs):
        r = MagicMock()
        r.text = second_response
        r.model = "m"
        r.provider = "p"
        r.usage = {}
        return r

    registry = ToolRegistry()
    registry.register(_CapsTool())

    memory = MagicMock()
    workspace = MagicMock()
    workspace.to_system_prompt.return_value = "sys"

    return CognitivePipeline(
        router=MagicMock(generate=_gen),
        memory=memory,
        workspace=workspace,
        tool_registry=registry,
    )


class TestRunToolIfCalled:
    @pytest.mark.asyncio
    async def test_returns_original_when_no_tool_call(self) -> None:
        p = _make_pipeline()
        text, used = await p._run_tool_if_called("No tool here", "user", "sys", "general")
        assert text == "No tool here"
        assert used is False

    @pytest.mark.asyncio
    async def test_returns_true_when_tool_was_called(self) -> None:
        p = _make_pipeline()
        first = 'TOOL_CALL: {"name": "caps", "arguments": {"text": "hello"}}'
        _, used = await p._run_tool_if_called(first, "user", "sys", "general")
        assert used is True

    @pytest.mark.asyncio
    async def test_returns_re_generated_text(self) -> None:
        p = _make_pipeline(second_response="FINAL")
        first = 'TOOL_CALL: {"name": "caps", "arguments": {"text": "hi"}}'
        text, _ = await p._run_tool_if_called(first, "user", "sys", "general")
        assert text == "FINAL"

    @pytest.mark.asyncio
    async def test_returns_original_when_registry_is_none(self) -> None:
        p = CognitivePipeline(
            router=MagicMock(),
            memory=MagicMock(),
            workspace=MagicMock(),
            tool_registry=None,
        )
        text, used = await p._run_tool_if_called(
            'TOOL_CALL: {"name": "caps", "arguments": {}}', "user", "sys", "general"
        )
        assert used is False
        assert "TOOL_CALL:" in text

    @pytest.mark.asyncio
    async def test_returns_false_on_malformed_json(self) -> None:
        p = _make_pipeline()
        _, used = await p._run_tool_if_called("TOOL_CALL: {bad}", "user", "sys", "general")
        assert used is False

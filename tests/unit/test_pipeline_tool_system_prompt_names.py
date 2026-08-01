"""Tests that the tool system prompt block contains registered tool names."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.pipeline import CognitivePipeline, _tools_system_block
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _ToolA(Tool):
    name = "tool_alpha"
    description = "Alpha tool for testing."
    parameters = {}
    permissions: list[str] = []

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output="a")


class _ToolB(Tool):
    name = "tool_beta"
    description = "Beta tool for testing."
    parameters = {}
    permissions: list[str] = []

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output="b")


class TestPipelineToolSystemPromptNames:
    def test_block_contains_single_tool_name(self) -> None:
        registry = ToolRegistry()
        registry.register(_ToolA())
        block = _tools_system_block(registry)
        assert "tool_alpha" in block

    def test_block_contains_all_tool_names(self) -> None:
        registry = ToolRegistry()
        registry.register(_ToolA())
        registry.register(_ToolB())
        block = _tools_system_block(registry)
        assert "tool_alpha" in block
        assert "tool_beta" in block

    def test_block_contains_tool_description(self) -> None:
        registry = ToolRegistry()
        registry.register(_ToolA())
        block = _tools_system_block(registry)
        assert "Alpha tool for testing" in block

    def test_system_prompt_contains_tool_names_via_build_system(self) -> None:
        registry = ToolRegistry()
        registry.register(_ToolA())
        registry.register(_ToolB())
        workspace = MagicMock()
        workspace.to_system_prompt.return_value = "You are helpful."
        p = CognitivePipeline(
            router=MagicMock(),
            memory=MagicMock(),
            workspace=workspace,
            tool_registry=registry,
        )
        ctx = MagicMock()
        ctx.to_prompt_blocks.return_value = []
        session = MagicMock()
        system = p._build_system(ctx, session)
        assert "tool_alpha" in system
        assert "tool_beta" in system

    def test_system_prompt_contains_call_protocol_example(self) -> None:
        registry = ToolRegistry()
        registry.register(_ToolA())
        workspace = MagicMock()
        workspace.to_system_prompt.return_value = "sys"
        p = CognitivePipeline(
            router=MagicMock(),
            memory=MagicMock(),
            workspace=workspace,
            tool_registry=registry,
        )
        ctx = MagicMock()
        ctx.to_prompt_blocks.return_value = []
        session = MagicMock()
        system = p._build_system(ctx, session)
        assert "tool_name" in system

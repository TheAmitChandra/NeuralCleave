"""Tests that CognitivePipeline injects the tool catalogue into the system prompt."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.pipeline import CognitivePipeline, _tools_system_block
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _FakeTool(Tool):
    name = "fake_search"
    description = "A fake search tool for testing."
    parameters = {}
    permissions: list[str] = []

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output="result")


def _make_pipeline_with_registry() -> CognitivePipeline:
    registry = ToolRegistry()
    registry.register(_FakeTool())
    workspace = MagicMock()
    workspace.to_system_prompt.return_value = "You are a helpful assistant."
    return CognitivePipeline(
        router=MagicMock(),
        memory=MagicMock(),
        workspace=workspace,
        tool_registry=registry,
    )


class TestPipelineToolPromptInjection:
    def test_tools_system_block_contains_tool_name(self) -> None:
        registry = ToolRegistry()
        registry.register(_FakeTool())
        block = _tools_system_block(registry)
        assert "fake_search" in block

    def test_tools_system_block_contains_tool_call_marker(self) -> None:
        registry = ToolRegistry()
        registry.register(_FakeTool())
        block = _tools_system_block(registry)
        assert "TOOL_CALL:" in block

    def test_tools_system_block_has_tools_header(self) -> None:
        registry = ToolRegistry()
        registry.register(_FakeTool())
        block = _tools_system_block(registry)
        assert "# Tools" in block

    def test_build_system_includes_tool_block_when_tools_registered(self) -> None:
        p = _make_pipeline_with_registry()
        ctx = MagicMock()
        ctx.to_prompt_blocks.return_value = []
        session = MagicMock()
        result = p._build_system(ctx, session)
        assert "TOOL_CALL:" in result

    def test_build_system_excludes_tool_block_when_no_registry(self) -> None:
        workspace = MagicMock()
        workspace.to_system_prompt.return_value = "You are helpful."
        p = CognitivePipeline(
            router=MagicMock(),
            memory=MagicMock(),
            workspace=workspace,
            tool_registry=None,
        )
        ctx = MagicMock()
        ctx.to_prompt_blocks.return_value = []
        session = MagicMock()
        result = p._build_system(ctx, session)
        assert "TOOL_CALL:" not in result

    def test_build_system_excludes_tool_block_when_registry_empty(self) -> None:
        workspace = MagicMock()
        workspace.to_system_prompt.return_value = "You are helpful."
        p = CognitivePipeline(
            router=MagicMock(),
            memory=MagicMock(),
            workspace=workspace,
            tool_registry=ToolRegistry(),
        )
        ctx = MagicMock()
        ctx.to_prompt_blocks.return_value = []
        session = MagicMock()
        result = p._build_system(ctx, session)
        assert "TOOL_CALL:" not in result

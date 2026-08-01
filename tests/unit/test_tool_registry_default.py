"""Tests for ToolRegistry.default() classmethod."""

from __future__ import annotations

from neuralcleave.tools.registry import ToolRegistry
from neuralcleave.tools.web_search import WebSearchTool
from neuralcleave.tools.file_ops import FileOpsTool
from neuralcleave.tools.shell import ShellTool


class TestToolRegistryDefault:
    def test_default_returns_registry(self) -> None:
        registry = ToolRegistry.default()
        assert isinstance(registry, ToolRegistry)

    def test_default_contains_web_search(self) -> None:
        registry = ToolRegistry.default()
        assert "web_search" in registry.names

    def test_default_contains_file_ops(self) -> None:
        registry = ToolRegistry.default()
        assert "file_ops" in registry.names

    def test_default_contains_shell(self) -> None:
        registry = ToolRegistry.default()
        assert "shell" in registry.names

    def test_web_search_is_correct_type(self) -> None:
        registry = ToolRegistry.default()
        tool = registry.get("web_search")
        assert isinstance(tool, WebSearchTool)

    def test_file_ops_is_correct_type(self) -> None:
        registry = ToolRegistry.default()
        tool = registry.get("file_ops")
        assert isinstance(tool, FileOpsTool)

    def test_shell_is_correct_type(self) -> None:
        registry = ToolRegistry.default()
        tool = registry.get("shell")
        assert isinstance(tool, ShellTool)

    def test_default_has_nonempty_names(self) -> None:
        registry = ToolRegistry.default()
        assert len(registry.names) > 0

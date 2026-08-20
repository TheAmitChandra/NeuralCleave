"""Tests for ToolRegistry.default() classmethod."""

from __future__ import annotations

from neuralcleave.tools.browser import BrowserAutomationTool
from neuralcleave.tools.file_ops import FileOpsTool
from neuralcleave.tools.image_generation import ImageGenerationTool
from neuralcleave.tools.registry import ToolRegistry
from neuralcleave.tools.shell import ShellTool
from neuralcleave.tools.web_search import WebSearchTool
from neuralcleave.tools.write_skill_tool import (
    DeleteSkillTool,
    ListSkillsTool,
    WriteSkillTool,
)


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

    def test_default_contains_browser(self) -> None:
        registry = ToolRegistry.default()
        assert "browser" in registry.names

    def test_browser_is_correct_type(self) -> None:
        registry = ToolRegistry.default()
        tool = registry.get("browser")
        assert isinstance(tool, BrowserAutomationTool)

    def test_default_contains_image_generation(self) -> None:
        registry = ToolRegistry.default()
        assert "image_generation" in registry.names

    def test_image_generation_is_correct_type(self) -> None:
        registry = ToolRegistry.default()
        tool = registry.get("image_generation")
        assert isinstance(tool, ImageGenerationTool)

    def test_default_contains_write_skill(self) -> None:
        """Regression guard: before P8, WriteSkillTool was never wired into
        the default registry at all — self-modifying skills were completely
        unreachable by the live agent regardless of the review gate."""
        registry = ToolRegistry.default()
        assert "write_skill" in registry.names

    def test_write_skill_is_correct_type(self) -> None:
        registry = ToolRegistry.default()
        tool = registry.get("write_skill")
        assert isinstance(tool, WriteSkillTool)

    def test_default_contains_list_skills(self) -> None:
        registry = ToolRegistry.default()
        assert "list_skills" in registry.names

    def test_list_skills_is_correct_type(self) -> None:
        registry = ToolRegistry.default()
        tool = registry.get("list_skills")
        assert isinstance(tool, ListSkillsTool)

    def test_default_contains_delete_skill(self) -> None:
        registry = ToolRegistry.default()
        assert "delete_skill" in registry.names

    def test_delete_skill_is_correct_type(self) -> None:
        registry = ToolRegistry.default()
        tool = registry.get("delete_skill")
        assert isinstance(tool, DeleteSkillTool)

    def test_write_skill_and_list_skills_share_the_same_writer(self) -> None:
        """The three skill tools should operate on one shared SkillWriter
        instance, not three independent ones with disjoint in-memory state."""
        registry = ToolRegistry.default()
        write_tool = registry.get("write_skill")
        list_tool = registry.get("list_skills")
        assert write_tool._writer is list_tool._writer

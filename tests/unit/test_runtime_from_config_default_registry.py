"""Tests that from_config() creates a default ToolRegistry with built-in tools."""

from __future__ import annotations

from unittest.mock import patch

from neuralcleave.config import NeuralCleaveConfig
from neuralcleave.tools.registry import ToolRegistry


def _capture_registry() -> ToolRegistry | None:
    cfg = NeuralCleaveConfig()
    captured: list[ToolRegistry] = []

    original_cls = None

    def _capture_pipeline(**kwargs):
        registry = kwargs.get("tool_registry")
        if registry is not None:
            captured.append(registry)
        mock = object.__new__(object)
        return mock

    with (
        patch("neuralcleave.agent.runtime.ModelRouter"),
        patch("neuralcleave.agent.runtime.MemoryRetrievalPipeline"),
        patch("neuralcleave.agent.runtime.CognitivePipeline", side_effect=_capture_pipeline),
        patch("neuralcleave.agent.runtime.SessionManager"),
        patch("neuralcleave.agent.runtime.LongTermMemory"),
        patch("neuralcleave.agent.runtime.WorkspaceLoader"),
        patch("neuralcleave.agent.runtime._build_adapters", return_value=[]),
    ):
        from neuralcleave.agent.runtime import AgentRuntime
        try:
            AgentRuntime.from_config(cfg)
        except Exception:
            pass

    return captured[0] if captured else None


class TestRuntimeFromConfigDefaultRegistry:
    def test_default_registry_has_web_search_tool(self) -> None:
        registry = _capture_registry()
        assert registry is not None
        assert "web_search" in registry.names

    def test_default_registry_has_file_ops_tool(self) -> None:
        registry = _capture_registry()
        assert registry is not None
        assert "file_ops" in registry.names

    def test_default_registry_has_shell_tool(self) -> None:
        registry = _capture_registry()
        assert registry is not None
        assert "shell" in registry.names

    def test_default_registry_has_at_least_three_tools(self) -> None:
        registry = _capture_registry()
        assert registry is not None
        assert len(registry.names) >= 3

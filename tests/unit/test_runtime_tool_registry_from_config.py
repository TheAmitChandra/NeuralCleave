"""Tests that AgentRuntime.from_config() wires a ToolRegistry into the pipeline."""

from __future__ import annotations

from unittest.mock import patch

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.config import NeuralCleaveConfig
from neuralcleave.tools.registry import ToolRegistry


def _patched_from_config():
    cfg = NeuralCleaveConfig()
    with (
        patch("neuralcleave.agent.runtime.ModelRouter"),
        patch("neuralcleave.agent.runtime.MemoryRetrievalPipeline"),
        patch("neuralcleave.agent.runtime.CognitivePipeline") as mock_pipeline_cls,
        patch("neuralcleave.agent.runtime.SessionManager"),
        patch("neuralcleave.agent.runtime.LongTermMemory"),
        patch("neuralcleave.agent.runtime.WorkspaceLoader"),
        patch("neuralcleave.agent.runtime._build_adapters", return_value=[]),
    ):
        mock_pipeline_cls.return_value = mock_pipeline_cls
        from neuralcleave.agent.runtime import AgentRuntime
        rt = AgentRuntime.from_config(cfg)
        call_kwargs = mock_pipeline_cls.call_args
        return rt, call_kwargs


class TestRuntimeToolRegistryFromConfig:
    def test_pipeline_receives_tool_registry_kwarg(self) -> None:
        _, call_kwargs = _patched_from_config()
        assert call_kwargs is not None
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
        if not kwargs:
            # positional args case
            kwargs = dict(zip(
                ["router", "memory", "workspace", "agent_name", "reflection", "tool_registry"],
                call_kwargs.args,
            ))
        assert "tool_registry" in kwargs

    def test_tool_registry_kwarg_is_not_none(self) -> None:
        _, call_kwargs = _patched_from_config()
        kwargs = call_kwargs.kwargs or {}
        tool_registry = kwargs.get("tool_registry")
        assert tool_registry is not None

    def test_tool_registry_is_registry_instance(self) -> None:
        _, call_kwargs = _patched_from_config()
        kwargs = call_kwargs.kwargs or {}
        tool_registry = kwargs.get("tool_registry")
        assert isinstance(tool_registry, ToolRegistry)

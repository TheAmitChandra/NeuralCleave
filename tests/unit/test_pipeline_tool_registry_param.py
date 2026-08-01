"""Tests that CognitivePipeline accepts and stores the tool_registry param."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.tools.registry import ToolRegistry


def _make_pipeline(tool_registry=None) -> CognitivePipeline:
    return CognitivePipeline(
        router=MagicMock(),
        memory=MagicMock(),
        workspace=MagicMock(),
        tool_registry=tool_registry,
    )


class TestPipelineToolRegistryParam:
    def test_accepts_none(self) -> None:
        p = _make_pipeline(tool_registry=None)
        assert p._tool_registry is None

    def test_accepts_registry_instance(self) -> None:
        registry = ToolRegistry()
        p = _make_pipeline(tool_registry=registry)
        assert p._tool_registry is registry

    def test_default_is_none(self) -> None:
        p = CognitivePipeline(
            router=MagicMock(),
            memory=MagicMock(),
            workspace=MagicMock(),
        )
        assert p._tool_registry is None

    def test_stores_provided_registry(self) -> None:
        registry = ToolRegistry()
        p = _make_pipeline(tool_registry=registry)
        assert p._tool_registry is not None

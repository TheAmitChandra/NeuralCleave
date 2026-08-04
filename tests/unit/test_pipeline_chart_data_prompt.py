"""Tests that the tools system block includes CHART_DATA inline-chart instructions."""

from __future__ import annotations

from neuralcleave.agent.pipeline import _tools_system_block
from neuralcleave.tools.registry import ToolRegistry


class TestPipelineChartDataPrompt:
    def _block(self) -> str:
        return _tools_system_block(ToolRegistry())

    def test_chart_data_marker_present(self) -> None:
        assert "CHART_DATA:" in self._block()

    def test_chart_data_type_field_documented(self) -> None:
        block = self._block()
        assert '"type"' in block
        assert '"bar"' in block or "bar" in block

    def test_chart_data_labels_and_values_documented(self) -> None:
        block = self._block()
        assert '"labels"' in block
        assert '"values"' in block

    def test_chart_data_line_instruction(self) -> None:
        assert "on its own line" in self._block()

    def test_chart_data_use_when_chart_requested(self) -> None:
        block = self._block()
        assert "chart" in block.lower()
        assert "graph" in block.lower() or "visual" in block.lower()

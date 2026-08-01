"""Tests for call_parser.parse() returning first call when multiple markers present."""

from __future__ import annotations

from neuralcleave.tools.call_parser import parse


class TestCallParserMultiple:
    def test_returns_first_call_when_two_present(self) -> None:
        text = (
            'TOOL_CALL: {"name": "web_search", "arguments": {"query": "first"}}\n'
            'TOOL_CALL: {"name": "shell", "arguments": {"command": "ls"}}'
        )
        result = parse(text)
        assert result is not None
        assert result.name == "web_search"

    def test_second_call_ignored(self) -> None:
        text = (
            'TOOL_CALL: {"name": "web_search", "arguments": {"query": "first"}}\n'
            'TOOL_CALL: {"name": "shell", "arguments": {"command": "ls"}}'
        )
        result = parse(text)
        assert result is not None
        assert result.name != "shell"

    def test_first_call_arguments_returned(self) -> None:
        text = (
            'TOOL_CALL: {"name": "web_search", "arguments": {"query": "first"}}\n'
            'TOOL_CALL: {"name": "file_ops", "arguments": {"operation": "read", "path": "a.txt"}}'
        )
        result = parse(text)
        assert result is not None
        assert result.arguments == {"query": "first"}

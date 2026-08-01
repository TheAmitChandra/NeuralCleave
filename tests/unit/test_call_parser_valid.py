"""Tests for call_parser.parse() with valid TOOL_CALL markers."""

from __future__ import annotations

from neuralcleave.tools.call_parser import ParsedToolCall, parse


class TestCallParserValid:
    def test_returns_parsed_tool_call(self) -> None:
        text = 'TOOL_CALL: {"name": "web_search", "arguments": {"query": "python"}}'
        result = parse(text)
        assert isinstance(result, ParsedToolCall)

    def test_name_extracted(self) -> None:
        text = 'TOOL_CALL: {"name": "web_search", "arguments": {"query": "python"}}'
        result = parse(text)
        assert result is not None
        assert result.name == "web_search"

    def test_arguments_extracted(self) -> None:
        text = 'TOOL_CALL: {"name": "web_search", "arguments": {"query": "python"}}'
        result = parse(text)
        assert result is not None
        assert result.arguments == {"query": "python"}

    def test_raw_contains_original_line(self) -> None:
        line = 'TOOL_CALL: {"name": "web_search", "arguments": {"query": "python"}}'
        result = parse(line)
        assert result is not None
        assert "TOOL_CALL:" in result.raw

    def test_parses_with_surrounding_text(self) -> None:
        text = (
            "I will search the web for you.\n"
            'TOOL_CALL: {"name": "web_search", "arguments": {"query": "news"}}\n'
            "Searching now..."
        )
        result = parse(text)
        assert result is not None
        assert result.name == "web_search"

    def test_parses_multiple_argument_fields(self) -> None:
        text = 'TOOL_CALL: {"name": "file_ops", "arguments": {"operation": "read", "path": "notes.txt"}}'
        result = parse(text)
        assert result is not None
        assert result.arguments["operation"] == "read"
        assert result.arguments["path"] == "notes.txt"

    def test_tool_name_shell(self) -> None:
        text = 'TOOL_CALL: {"name": "shell", "arguments": {"command": "ls"}}'
        result = parse(text)
        assert result is not None
        assert result.name == "shell"

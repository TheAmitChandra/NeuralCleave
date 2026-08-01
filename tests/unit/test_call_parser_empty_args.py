"""Tests for call_parser.parse() with absent or empty arguments field."""

from __future__ import annotations

from neuralcleave.tools.call_parser import parse


class TestCallParserEmptyArgs:
    def test_empty_arguments_dict_returned_as_dict(self) -> None:
        text = 'TOOL_CALL: {"name": "web_search", "arguments": {}}'
        result = parse(text)
        assert result is not None
        assert result.arguments == {}

    def test_absent_arguments_field_defaults_to_empty_dict(self) -> None:
        text = 'TOOL_CALL: {"name": "web_search"}'
        result = parse(text)
        assert result is not None
        assert result.arguments == {}

    def test_non_dict_arguments_coerced_to_empty_dict(self) -> None:
        text = 'TOOL_CALL: {"name": "web_search", "arguments": "bad"}'
        result = parse(text)
        assert result is not None
        assert result.arguments == {}

    def test_null_arguments_coerced_to_empty_dict(self) -> None:
        text = 'TOOL_CALL: {"name": "web_search", "arguments": null}'
        result = parse(text)
        assert result is not None
        assert result.arguments == {}

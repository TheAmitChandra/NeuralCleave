"""Tests for call_parser.parse() returning None when name field is missing or invalid."""

from __future__ import annotations

from neuralcleave.tools.call_parser import parse


class TestCallParserMissingName:
    def test_returns_none_when_name_absent(self) -> None:
        assert parse('TOOL_CALL: {"arguments": {"query": "test"}}') is None

    def test_returns_none_when_name_is_empty_string(self) -> None:
        assert parse('TOOL_CALL: {"name": "", "arguments": {}}') is None

    def test_returns_none_when_name_is_null(self) -> None:
        assert parse('TOOL_CALL: {"name": null, "arguments": {}}') is None

    def test_returns_none_when_name_is_integer(self) -> None:
        assert parse('TOOL_CALL: {"name": 42, "arguments": {}}') is None

    def test_returns_none_when_name_is_list(self) -> None:
        assert parse('TOOL_CALL: {"name": ["web_search"], "arguments": {}}') is None

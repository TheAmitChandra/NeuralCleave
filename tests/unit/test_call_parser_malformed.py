"""Tests for call_parser.parse() returning None when JSON is malformed."""

from __future__ import annotations

from neuralcleave.tools.call_parser import parse


class TestCallParserMalformed:
    def test_returns_none_for_truncated_json(self) -> None:
        assert parse("TOOL_CALL: {\"name\": \"web_search\"") is None

    def test_returns_none_for_single_quotes_json(self) -> None:
        assert parse("TOOL_CALL: {'name': 'web_search', 'arguments': {}}") is None

    def test_returns_none_for_bare_value(self) -> None:
        assert parse("TOOL_CALL: web_search") is None

    def test_returns_none_for_array_instead_of_object(self) -> None:
        assert parse('TOOL_CALL: ["web_search"]') is None

    def test_returns_none_for_empty_braces(self) -> None:
        assert parse("TOOL_CALL: {}") is None

    def test_returns_none_for_no_closing_brace(self) -> None:
        assert parse('TOOL_CALL: {"name": "web_search"') is None

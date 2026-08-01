"""Tests for call_parser.parse() returning None when no TOOL_CALL marker is present."""

from __future__ import annotations

from neuralcleave.tools.call_parser import parse


class TestCallParserNoCall:
    def test_returns_none_for_empty_string(self) -> None:
        assert parse("") is None

    def test_returns_none_for_plain_text(self) -> None:
        assert parse("Hello, how can I help you today?") is None

    def test_returns_none_for_partial_marker(self) -> None:
        assert parse("TOOL_CALL") is None

    def test_returns_none_when_marker_has_no_json(self) -> None:
        assert parse("TOOL_CALL: nothing here") is None

    def test_returns_none_for_lowercase_marker(self) -> None:
        assert parse('tool_call: {"name": "web_search", "arguments": {}}') is None

    def test_returns_none_for_multiline_without_marker(self) -> None:
        text = "Line one\nLine two\nLine three"
        assert parse(text) is None

    def test_returns_none_for_similar_but_wrong_prefix(self) -> None:
        assert parse('TOOLCALL: {"name": "web_search", "arguments": {}}') is None

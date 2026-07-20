"""Unit tests for neuralcleave_google_calendar.plugin — GoogleCalendarPlugin."""

from __future__ import annotations

from neuralcleave_google_calendar.plugin import GoogleCalendarPlugin
from neuralcleave_google_calendar.tool import GoogleCalendarEventsTool


def test_plugin_metadata():
    p = GoogleCalendarPlugin()
    assert p.metadata.name == "neuralcleave-google-calendar"
    assert p.metadata.plugin_type == "tool"


def test_plugin_reads_token_from_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_ACCESS_TOKEN", "ya29.fromenv")
    p = GoogleCalendarPlugin()
    assert p._access_token == "ya29.fromenv"


def test_plugin_no_token_in_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_CALENDAR_ACCESS_TOKEN", raising=False)
    p = GoogleCalendarPlugin()
    assert p._access_token is None


def test_get_tools_returns_calendar_events_tool():
    tools = GoogleCalendarPlugin().get_tools()
    assert len(tools) == 1
    assert isinstance(tools[0], GoogleCalendarEventsTool)


def test_get_tools_tool_carries_plugin_token(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_ACCESS_TOKEN", "ya29.carried")
    tool = GoogleCalendarPlugin().get_tools()[0]
    assert tool._access_token == "ya29.carried"

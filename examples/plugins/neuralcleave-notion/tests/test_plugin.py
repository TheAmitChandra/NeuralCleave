"""Unit tests for neuralcleave_notion.plugin — NotionPlugin."""

from __future__ import annotations

from neuralcleave_notion.plugin import NotionPlugin
from neuralcleave_notion.tool import NotionSearchTool


def test_plugin_metadata():
    p = NotionPlugin()
    assert p.metadata.name == "neuralcleave-notion"
    assert p.metadata.plugin_type == "tool"


def test_plugin_reads_token_from_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret_fromenv")
    p = NotionPlugin()
    assert p._token == "secret_fromenv"


def test_plugin_no_token_in_env(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    p = NotionPlugin()
    assert p._token is None


def test_get_tools_returns_notion_search_tool():
    tools = NotionPlugin().get_tools()
    assert len(tools) == 1
    assert isinstance(tools[0], NotionSearchTool)


def test_get_tools_tool_carries_plugin_token(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret_carried")
    tool = NotionPlugin().get_tools()[0]
    assert tool._token == "secret_carried"

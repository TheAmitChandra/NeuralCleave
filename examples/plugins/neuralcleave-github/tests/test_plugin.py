"""Unit tests for cortexflow_github.plugin — GitHubPlugin."""

from __future__ import annotations

from cortexflow_github.plugin import GitHubPlugin
from cortexflow_github.tool import GitHubEventsTool


def test_plugin_metadata():
    p = GitHubPlugin()
    assert p.metadata.name == "cortexflow-github"
    assert p.metadata.plugin_type == "tool"
    assert "network" in p.metadata.permissions


def test_plugin_reads_token_from_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fromenv")
    p = GitHubPlugin()
    assert p._token == "ghp_fromenv"


def test_plugin_no_token_in_env(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    p = GitHubPlugin()
    assert p._token is None


def test_get_tools_returns_github_events_tool():
    tools = GitHubPlugin().get_tools()
    assert len(tools) == 1
    assert isinstance(tools[0], GitHubEventsTool)


def test_get_tools_tool_carries_plugin_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_carried")
    tool = GitHubPlugin().get_tools()[0]
    assert tool._token == "ghp_carried"

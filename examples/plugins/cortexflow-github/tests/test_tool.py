"""Unit tests for cortexflow_github.tool — GitHubEventsTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cortexflow_github.tool import GitHubEventsTool

_SAMPLE_EVENTS = [
    {"type": "PushEvent", "actor": {"login": "alice"}, "created_at": "2026-06-26T10:00:00Z"},
    {"type": "IssuesEvent", "actor": {"login": "bob"}, "created_at": "2026-06-26T09:00:00Z"},
]


def _make_mock_client(json_body, raise_on_status: Exception | None = None):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=raise_on_status)
    mock_resp.json = MagicMock(return_value=json_body)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)
    return mock_client


@pytest.mark.asyncio
async def test_execute_returns_formatted_events():
    tool = GitHubEventsTool()
    mock_client = _make_mock_client(_SAMPLE_EVENTS)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute(owner="TheAmitChandra", repo="CortexFlow", limit=10)

    assert result.success
    assert len(result.output) == 2
    assert result.output[0]["actor"] == "alice"
    assert result.metadata["repo"] == "TheAmitChandra/CortexFlow"


@pytest.mark.asyncio
async def test_execute_respects_limit():
    tool = GitHubEventsTool()
    mock_client = _make_mock_client(_SAMPLE_EVENTS)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute(owner="o", repo="r", limit=1)

    assert len(result.output) == 1


@pytest.mark.asyncio
async def test_execute_sends_auth_header_when_token_set():
    tool = GitHubEventsTool(token="ghp_secret")
    mock_client = _make_mock_client(_SAMPLE_EVENTS)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await tool.execute(owner="o", repo="r")

    call_kwargs = mock_client.get.call_args[1]
    assert call_kwargs["headers"]["Authorization"] == "Bearer ghp_secret"


@pytest.mark.asyncio
async def test_execute_no_token_omits_auth_header():
    tool = GitHubEventsTool()
    mock_client = _make_mock_client(_SAMPLE_EVENTS)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await tool.execute(owner="o", repo="r")

    call_kwargs = mock_client.get.call_args[1]
    assert call_kwargs["headers"] == {}


@pytest.mark.asyncio
async def test_execute_http_error_returns_error_result():
    tool = GitHubEventsTool()
    mock_client = _make_mock_client([], raise_on_status=RuntimeError("404 Not Found"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute(owner="o", repo="missing")

    assert not result.success
    assert "404" in result.error


@pytest.mark.asyncio
async def test_execute_missing_httpx_returns_error():
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return real_import(name, *args, **kwargs)

    tool = GitHubEventsTool()
    with patch("builtins.__import__", side_effect=fake_import):
        result = await tool.execute(owner="o", repo="r")

    assert not result.success
    assert "pip install httpx" in result.error


def test_tool_schema_marks_owner_and_repo_required():
    schema = GitHubEventsTool().get_schema()
    assert "owner" in schema["parameters"]["required"]
    assert "repo" in schema["parameters"]["required"]
    assert "limit" not in schema["parameters"]["required"]

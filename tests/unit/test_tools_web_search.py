"""Unit tests for cortexflow.tools.web_search — WebSearchTool (all HTTP mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow.tools.web_search import WebSearchTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DDG_RESPONSE = {
    "AbstractText": "Python is a programming language.",
    "Heading": "Python",
    "AbstractURL": "https://example.com/python",
    "RelatedTopics": [
        {"Text": "Python tutorial", "FirstURL": "https://example.com/tut"},
        {"Text": "Python docs", "FirstURL": "https://example.com/docs"},
    ],
    "Results": [],
}

_SEARXNG_RESPONSE = {
    "results": [
        {"title": "SearXNG result 1", "url": "https://s1.com", "content": "content 1"},
        {"title": "SearXNG result 2", "url": "https://s2.com", "content": "content 2"},
    ]
}


def _make_mock_response(json_data: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    resp.status_code = status
    return resp


# ---------------------------------------------------------------------------
# Basic metadata
# ---------------------------------------------------------------------------


def test_web_search_name_and_permissions():
    tool = WebSearchTool()
    assert tool.name == "web_search"
    assert "network" in tool.permissions


def test_web_search_schema_has_query():
    schema = WebSearchTool().get_schema()
    assert "query" in schema["parameters"]["properties"]


def test_web_search_schema_query_required():
    schema = WebSearchTool().get_schema()
    assert "query" in schema["parameters"]["required"]


def test_web_search_schema_max_results_optional():
    schema = WebSearchTool().get_schema()
    assert "max_results" not in schema["parameters"]["required"]


# ---------------------------------------------------------------------------
# DuckDuckGo path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_search_ddg_returns_results():
    tool = WebSearchTool()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_make_mock_response(_DDG_RESPONSE))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_httpx = MagicMock()
    mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"httpx": mock_httpx}):
        result = await tool.execute(query="Python")

    assert result.success
    assert isinstance(result.output, list)
    assert len(result.output) >= 1
    assert result.output[0]["title"] == "Python"


@pytest.mark.asyncio
async def test_web_search_ddg_empty_response_returns_empty_list():
    tool = WebSearchTool()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_make_mock_response({"AbstractText": "", "RelatedTopics": [], "Results": []}))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_httpx = MagicMock()
    mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"httpx": mock_httpx}):
        result = await tool.execute(query="xyzzy")

    assert result.success
    assert result.output == []


@pytest.mark.asyncio
async def test_web_search_max_results_clamped_to_1():
    tool = WebSearchTool()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_make_mock_response(_DDG_RESPONSE))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_httpx = MagicMock()
    mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"httpx": mock_httpx}):
        result = await tool.execute(query="Python", max_results=0)

    assert result.success
    assert len(result.output) <= 1


@pytest.mark.asyncio
async def test_web_search_max_results_clamped_to_10():
    tool = WebSearchTool()
    many_topics = [{"Text": f"Topic {i}", "FirstURL": f"https://ex.com/{i}"} for i in range(20)]
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_make_mock_response(
        {"AbstractText": "", "AbstractURL": "", "Heading": "", "RelatedTopics": many_topics, "Results": []}
    ))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_httpx = MagicMock()
    mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"httpx": mock_httpx}):
        result = await tool.execute(query="Python", max_results=99)

    assert result.success
    assert len(result.output) <= 10


@pytest.mark.asyncio
async def test_web_search_ddg_http_error_returns_error():
    tool = WebSearchTool()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_httpx = MagicMock()
    mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"httpx": mock_httpx}):
        result = await tool.execute(query="Python")

    assert not result.success
    assert result.error is not None


# ---------------------------------------------------------------------------
# SearXNG path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_search_uses_searxng_when_configured():
    tool = WebSearchTool(searxng_url="http://searx.local")
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_make_mock_response(_SEARXNG_RESPONSE))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_httpx = MagicMock()
    mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"httpx": mock_httpx}):
        result = await tool.execute(query="Python")

    assert result.success
    assert result.metadata.get("source") == "searxng"
    assert result.output[0]["title"] == "SearXNG result 1"


@pytest.mark.asyncio
async def test_web_search_falls_back_to_ddg_when_searxng_fails():
    tool = WebSearchTool(searxng_url="http://searx.local")
    call_count = 0

    async def _fake_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("searxng down")
        return _make_mock_response(_DDG_RESPONSE)

    mock_client = AsyncMock()
    mock_client.get = _fake_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_httpx = MagicMock()
    mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"httpx": mock_httpx}):
        result = await tool.execute(query="Python")

    assert result.success
    assert result.metadata.get("source") == "duckduckgo"


# ---------------------------------------------------------------------------
# Missing httpx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_search_missing_httpx_returns_error():
    tool = WebSearchTool()
    with patch.dict("sys.modules", {"httpx": None}):
        result = await tool.execute(query="Python")
    assert not result.success
    assert "httpx" in (result.error or "")

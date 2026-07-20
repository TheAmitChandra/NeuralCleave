"""Unit tests for neuralcleave_notion.tool — NotionSearchTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from neuralcleave_notion.tool import NotionSearchTool, _extract_title

_SAMPLE_RESULT = {
    "id": "page-1",
    "object": "page",
    "url": "https://notion.so/page-1",
    "properties": {
        "Name": {"type": "title", "title": [{"plain_text": "Q3 "}, {"plain_text": "Roadmap"}]},
    },
}


def _make_mock_client(json_body, raise_on_status: Exception | None = None):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=raise_on_status)
    mock_resp.json = MagicMock(return_value=json_body)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)
    return mock_client


def test_extract_title_joins_rich_text_segments():
    assert _extract_title(_SAMPLE_RESULT) == "Q3 Roadmap"


def test_extract_title_untitled_when_no_title_property():
    assert _extract_title({"properties": {}}) == "(untitled)"


@pytest.mark.asyncio
async def test_execute_no_token_returns_error():
    tool = NotionSearchTool(token=None)
    result = await tool.execute(query="x")
    assert not result.success
    assert "NOTION_TOKEN" in result.error


@pytest.mark.asyncio
async def test_execute_returns_formatted_results():
    tool = NotionSearchTool(token="secret_abc")
    mock_client = _make_mock_client({"results": [_SAMPLE_RESULT]})

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute(query="roadmap")

    assert result.success
    assert result.output[0]["title"] == "Q3 Roadmap"
    assert result.output[0]["type"] == "page"
    assert result.metadata["query"] == "roadmap"


@pytest.mark.asyncio
async def test_execute_sends_notion_version_header():
    tool = NotionSearchTool(token="secret_abc")
    mock_client = _make_mock_client({"results": []})

    with patch("httpx.AsyncClient", return_value=mock_client):
        await tool.execute(query="x")

    headers = mock_client.post.call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer secret_abc"
    assert headers["Notion-Version"] == "2022-06-28"


@pytest.mark.asyncio
async def test_execute_http_error_returns_error_result():
    tool = NotionSearchTool(token="secret_abc")
    mock_client = _make_mock_client({}, raise_on_status=RuntimeError("401 Unauthorized"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute(query="x")

    assert not result.success
    assert "401" in result.error


@pytest.mark.asyncio
async def test_execute_missing_httpx_returns_error():
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return real_import(name, *args, **kwargs)

    tool = NotionSearchTool(token="secret_abc")
    with patch("builtins.__import__", side_effect=fake_import):
        result = await tool.execute(query="x")

    assert not result.success
    assert "pip install httpx" in result.error

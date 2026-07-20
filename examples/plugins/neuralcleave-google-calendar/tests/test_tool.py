"""Unit tests for neuralcleave_google_calendar.tool — GoogleCalendarEventsTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from neuralcleave_google_calendar.tool import GoogleCalendarEventsTool

_SAMPLE_ITEMS = [
    {
        "summary": "Team standup",
        "start": {"dateTime": "2026-06-27T10:00:00Z"},
        "htmlLink": "https://calendar.google.com/event1",
    },
    {
        "summary": "All-day offsite",
        "start": {"date": "2026-06-28"},
        "htmlLink": "https://calendar.google.com/event2",
    },
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
async def test_execute_no_token_returns_error():
    tool = GoogleCalendarEventsTool(access_token=None)
    result = await tool.execute()
    assert not result.success
    assert "GOOGLE_CALENDAR_ACCESS_TOKEN" in result.error


@pytest.mark.asyncio
async def test_execute_returns_formatted_events():
    tool = GoogleCalendarEventsTool(access_token="ya29.token")
    mock_client = _make_mock_client({"items": _SAMPLE_ITEMS})

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute(calendar_id="primary", limit=10)

    assert result.success
    assert result.output[0]["summary"] == "Team standup"
    assert result.output[0]["start"] == "2026-06-27T10:00:00Z"
    assert result.metadata["calendar_id"] == "primary"


@pytest.mark.asyncio
async def test_execute_falls_back_to_all_day_date():
    tool = GoogleCalendarEventsTool(access_token="ya29.token")
    mock_client = _make_mock_client({"items": [_SAMPLE_ITEMS[1]]})

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute()

    assert result.output[0]["start"] == "2026-06-28"


@pytest.mark.asyncio
async def test_execute_missing_summary_uses_placeholder():
    tool = GoogleCalendarEventsTool(access_token="ya29.token")
    mock_client = _make_mock_client({"items": [{"start": {"date": "2026-06-29"}}]})

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute()

    assert result.output[0]["summary"] == "(no title)"


@pytest.mark.asyncio
async def test_execute_sends_bearer_token_and_ordering_params():
    tool = GoogleCalendarEventsTool(access_token="ya29.token")
    mock_client = _make_mock_client({"items": []})

    with patch("httpx.AsyncClient", return_value=mock_client):
        await tool.execute()

    call_kwargs = mock_client.get.call_args[1]
    assert call_kwargs["headers"]["Authorization"] == "Bearer ya29.token"
    assert call_kwargs["params"]["orderBy"] == "startTime"
    assert "timeMin" in call_kwargs["params"]


@pytest.mark.asyncio
async def test_execute_respects_limit():
    tool = GoogleCalendarEventsTool(access_token="ya29.token")
    mock_client = _make_mock_client({"items": _SAMPLE_ITEMS})

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute(limit=1)

    assert len(result.output) == 1


@pytest.mark.asyncio
async def test_execute_http_error_returns_error_result():
    tool = GoogleCalendarEventsTool(access_token="ya29.token")
    mock_client = _make_mock_client({}, raise_on_status=RuntimeError("403 Forbidden"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute()

    assert not result.success
    assert "403" in result.error


@pytest.mark.asyncio
async def test_execute_missing_httpx_returns_error():
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return real_import(name, *args, **kwargs)

    tool = GoogleCalendarEventsTool(access_token="ya29.token")
    with patch("builtins.__import__", side_effect=fake_import):
        result = await tool.execute()

    assert not result.success
    assert "pip install httpx" in result.error

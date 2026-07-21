"""Edge-case tests for neuralcleave.update_checker.

The base tests in test_update_checker.py cover the happy path.
These tests focus on: malformed responses, network failures, timeouts,
unusual version strings, and the httpx-missing branch.

Note: get_latest_version imports httpx *inside* the function body, so
async tests patch `httpx.AsyncClient` rather than a module attribute.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.update_checker import get_latest_version, is_newer, parse_version

# ---------------------------------------------------------------------------
# parse_version — edge cases
# ---------------------------------------------------------------------------


class TestParseVersionEdgeCases:
    def test_single_segment(self):
        assert parse_version("3") == (3,)

    def test_four_segment(self):
        assert parse_version("1.2.3.4") == (1, 2, 3, 4)

    def test_empty_string(self):
        assert parse_version("") == (0,)

    def test_all_non_numeric(self):
        assert parse_version("alpha.beta.gamma") == (0, 0, 0)

    def test_leading_zeros_are_parsed(self):
        assert parse_version("01.02.03") == (1, 2, 3)

    def test_segment_with_letters_and_digits(self):
        assert parse_version("2.0.0beta1") == (2, 0, 0)

    def test_segment_starting_with_non_digit(self):
        assert parse_version("2.0.rc1") == (2, 0, 0)

    def test_version_zero(self):
        assert parse_version("0.0.0") == (0, 0, 0)


# ---------------------------------------------------------------------------
# is_newer — edge cases
# ---------------------------------------------------------------------------


class TestIsNewerEdgeCases:
    def test_equal_versions_not_newer(self):
        assert is_newer("2.0.5", "2.0.5") is False

    def test_older_is_not_newer(self):
        assert is_newer("1.9.9", "2.0.0") is False

    def test_major_bump_is_newer(self):
        assert is_newer("3.0.0", "2.9.9") is True

    def test_different_length_shorter_newer(self):
        assert is_newer("2.1", "2.0.9") is True

    def test_different_length_longer_older(self):
        assert is_newer("2.0.0", "2.1") is False

    def test_pre_release_compared_as_int(self):
        # "2.0.0rc1" → (2, 0, 0), "2.0.0" → (2, 0, 0) → equal, not newer
        assert is_newer("2.0.0rc1", "2.0.0") is False


# ---------------------------------------------------------------------------
# Helpers for async mock AsyncClient
# ---------------------------------------------------------------------------


def _make_client_ctx(response_json=None, raise_on_get=None, raise_on_raise_for_status=None):
    """Build an AsyncMock context manager that mimics httpx.AsyncClient."""
    mock_response = MagicMock()
    if raise_on_raise_for_status:
        mock_response.raise_for_status = MagicMock(side_effect=raise_on_raise_for_status)
    else:
        mock_response.raise_for_status = MagicMock()

    if response_json is not None:
        mock_response.json = MagicMock(return_value=response_json)
    else:
        mock_response.json = MagicMock(return_value={})

    mock_client = AsyncMock()
    if raise_on_get:
        mock_client.get = AsyncMock(side_effect=raise_on_get)
    else:
        mock_client.get = AsyncMock(return_value=mock_response)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


# ---------------------------------------------------------------------------
# get_latest_version — network failure scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetLatestVersionNetworkFailures:
    async def test_returns_none_on_connection_error(self):
        ctx = _make_client_ctx(raise_on_get=ConnectionError("refused"))
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await get_latest_version("neuralcleave")
        assert result is None

    async def test_returns_none_on_timeout(self):
        import httpx as real_httpx

        ctx = _make_client_ctx(raise_on_get=real_httpx.TimeoutException("timed out"))
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await get_latest_version("neuralcleave")
        assert result is None

    async def test_returns_none_on_http_status_error(self):
        import httpx as real_httpx

        exc = real_httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock())
        ctx = _make_client_ctx(raise_on_raise_for_status=exc)
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await get_latest_version("neuralcleave")
        assert result is None

    async def test_returns_none_on_oserror(self):
        ctx = _make_client_ctx(raise_on_get=OSError("no route to host"))
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await get_latest_version("neuralcleave")
        assert result is None


# ---------------------------------------------------------------------------
# get_latest_version — malformed responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetLatestVersionMalformedResponse:
    async def test_returns_none_when_info_key_missing(self):
        ctx = _make_client_ctx(response_json={"releases": {}})
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await get_latest_version("neuralcleave")
        assert result is None

    async def test_returns_none_when_version_key_missing(self):
        ctx = _make_client_ctx(response_json={"info": {"name": "neuralcleave"}})
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await get_latest_version("neuralcleave")
        assert result is None

    async def test_returns_none_on_empty_json_object(self):
        ctx = _make_client_ctx(response_json={})
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await get_latest_version("neuralcleave")
        assert result is None

    async def test_returns_none_on_json_decode_error(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(side_effect=ValueError("not json"))
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_ctx):
            result = await get_latest_version("neuralcleave")
        assert result is None

    async def test_returns_version_string_when_valid(self):
        ctx = _make_client_ctx(response_json={"info": {"version": "3.0.0"}})
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await get_latest_version("neuralcleave")
        assert result == "3.0.0"

    async def test_timeout_param_passed_to_client(self):
        ctx = _make_client_ctx(response_json={"info": {"version": "1.0.0"}})
        with patch("httpx.AsyncClient", return_value=ctx) as mock_cls:
            await get_latest_version("neuralcleave", timeout=3.5)
        mock_cls.assert_called_once_with(timeout=3.5)


# ---------------------------------------------------------------------------
# get_latest_version — httpx not installed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetLatestVersionNoHttpx:
    async def test_returns_none_when_httpx_not_installed(self):
        real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def fake_import(name, *args, **kwargs):
            if name == "httpx":
                raise ImportError("no module named httpx")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = await get_latest_version("neuralcleave")

        assert result is None

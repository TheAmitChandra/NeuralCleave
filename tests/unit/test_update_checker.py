"""Unit tests for cortexflow.update_checker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow.update_checker import get_latest_version, is_newer, parse_version

# ---------------------------------------------------------------------------
# parse_version
# ---------------------------------------------------------------------------


def test_parse_version_simple():
    assert parse_version("2.0.0") == (2, 0, 0)


def test_parse_version_different_lengths():
    assert parse_version("2.1") == (2, 1)


def test_parse_version_strips_prerelease_suffix():
    assert parse_version("2.1.0-beta") == (2, 1, 0)


def test_parse_version_handles_rc_suffix():
    assert parse_version("1.2.3rc1") == (1, 2, 3)


def test_parse_version_non_numeric_segment_becomes_zero():
    assert parse_version("2.x.0") == (2, 0, 0)


# ---------------------------------------------------------------------------
# is_newer
# ---------------------------------------------------------------------------


def test_is_newer_true_for_higher_minor():
    assert is_newer("2.1.0", "2.0.0") is True


def test_is_newer_false_for_equal_versions():
    assert is_newer("2.0.0", "2.0.0") is False


def test_is_newer_false_for_lower_version():
    assert is_newer("1.9.9", "2.0.0") is False


def test_is_newer_true_for_higher_patch():
    assert is_newer("2.0.1", "2.0.0") is True


# ---------------------------------------------------------------------------
# get_latest_version
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_version_returns_version_on_success():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"info": {"version": "2.5.0"}})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        version = await get_latest_version("cortexflow")

    assert version == "2.5.0"


@pytest.mark.asyncio
async def test_get_latest_version_returns_none_on_http_error():
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("404 Not Found"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        version = await get_latest_version("nonexistent-package-xyz")

    assert version is None


@pytest.mark.asyncio
async def test_get_latest_version_returns_none_if_httpx_missing():
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("no httpx")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        version = await get_latest_version("cortexflow")

    assert version is None

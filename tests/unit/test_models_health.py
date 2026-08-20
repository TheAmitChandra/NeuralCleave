"""Tests for neuralcleave.models.health — provider credential + live
reachability probing (P6, 2026-08-17 gap analysis).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

import neuralcleave.models.health as health_module
from neuralcleave.models.health import PROVIDER_ORDER, ProviderStatus, check_providers
from neuralcleave.models.router import ModelRouter


def _mock_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, json={}, request=httpx.Request("GET", "http://x"))


def _patched_async_client(response=None, side_effect=None):
    mock_client = AsyncMock()
    if side_effect is not None:
        mock_client.get = AsyncMock(side_effect=side_effect)
    else:
        mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return patch.object(health_module.httpx, "AsyncClient", MagicMock(return_value=mock_client))


class TestProviderOrderAndConfigured:
    def test_provider_order_has_19_entries(self):
        assert len(PROVIDER_ORDER) == 19
        assert len(set(PROVIDER_ORDER)) == 19  # no duplicates

    def test_unconfigured_router_reports_false_for_key_based_providers(self):
        router = ModelRouter()
        statuses = {s.provider: s for s in _run(check_providers(router, live=False))}
        assert statuses["anthropic"].configured is False
        assert statuses["openai"].configured is False

    def test_configured_key_reports_true(self):
        router = ModelRouter(anthropic_api_key="sk-test-key")
        statuses = {s.provider: s for s in _run(check_providers(router, live=False))}
        assert statuses["anthropic"].configured is True

    def test_ollama_always_configured(self):
        router = ModelRouter()
        statuses = {s.provider: s for s in _run(check_providers(router, live=False))}
        assert statuses["ollama"].configured is True

    def test_bedrock_configured_is_none(self):
        router = ModelRouter()
        statuses = {s.provider: s for s in _run(check_providers(router, live=False))}
        assert statuses["bedrock"].configured is None

    def test_azure_requires_both_key_and_endpoint(self):
        router = ModelRouter(azure_api_key="key-only")
        statuses = {s.provider: s for s in _run(check_providers(router, live=False))}
        assert statuses["azure"].configured is False

    def test_azure_configured_with_key_and_endpoint(self):
        router = ModelRouter(azure_api_key="key", azure_endpoint="https://x.openai.azure.com")
        statuses = {s.provider: s for s in _run(check_providers(router, live=False))}
        assert statuses["azure"].configured is True


class TestNonLiveCheck:
    def test_no_network_calls_made(self):
        router = ModelRouter(openai_api_key="sk-test")
        with patch.object(health_module.httpx, "AsyncClient") as mock_client_cls:
            _run(check_providers(router, live=False))
        mock_client_cls.assert_not_called()

    def test_all_entries_have_live_checked_false(self):
        router = ModelRouter()
        statuses = _run(check_providers(router, live=False))
        assert all(s.live_checked is False for s in statuses)

    def test_all_entries_have_reachable_none(self):
        router = ModelRouter()
        statuses = _run(check_providers(router, live=False))
        assert all(s.reachable is None for s in statuses)


class TestLiveCheckOpenAICompatible:
    def test_configured_provider_reports_reachable_on_200(self):
        router = ModelRouter(openai_api_key="sk-test")
        with _patched_async_client(response=_mock_response(200)):
            statuses = {s.provider: s for s in _run(check_providers(router, live=True))}
        assert statuses["openai"].live_checked is True
        assert statuses["openai"].reachable is True

    def test_401_reports_credentials_rejected(self):
        router = ModelRouter(openai_api_key="sk-bad")
        with _patched_async_client(response=_mock_response(401)):
            statuses = {s.provider: s for s in _run(check_providers(router, live=True))}
        assert statuses["openai"].reachable is False
        assert "rejected" in statuses["openai"].detail.lower()

    def test_429_reports_rate_limited(self):
        router = ModelRouter(openai_api_key="sk-test")
        with _patched_async_client(response=_mock_response(429)):
            statuses = {s.provider: s for s in _run(check_providers(router, live=True))}
        assert "rate limited" in statuses["openai"].detail.lower()

    def test_timeout_reports_timed_out(self):
        router = ModelRouter(openai_api_key="sk-test")
        with _patched_async_client(side_effect=httpx.TimeoutException("timeout")):
            statuses = {s.provider: s for s in _run(check_providers(router, live=True))}
        assert statuses["openai"].reachable is False
        assert "timed out" in statuses["openai"].detail.lower()

    def test_connection_error_reports_detail(self):
        router = ModelRouter(openai_api_key="sk-test")
        with _patched_async_client(side_effect=httpx.ConnectError("refused")):
            statuses = {s.provider: s for s in _run(check_providers(router, live=True))}
        assert statuses["openai"].reachable is False

    def test_unconfigured_provider_skips_live_check(self):
        router = ModelRouter()  # no openai key
        with _patched_async_client(response=_mock_response(200)):  # covers ollama's incidental probe
            statuses = {s.provider: s for s in _run(check_providers(router, live=True))}
        assert statuses["openai"].live_checked is False
        assert statuses["openai"].reachable is None
        assert "not configured" in statuses["openai"].detail.lower()

    def test_unconfigured_providers_make_no_http_calls(self):
        # Only ollama is "configured" by default (always-on local default),
        # so exactly one AsyncClient should be constructed (for ollama) —
        # none of the unconfigured OpenAI-compatible providers should probe.
        router = ModelRouter()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(200))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch.object(health_module.httpx, "AsyncClient", MagicMock(return_value=mock_client)) as mock_client_cls:
            _run(check_providers(router, live=True))
        assert mock_client_cls.call_count == 1


class TestLiveCheckOllama:
    def test_reachable_on_200(self):
        router = ModelRouter()
        with _patched_async_client(response=_mock_response(200)):
            statuses = {s.provider: s for s in _run(check_providers(router, live=True))}
        assert statuses["ollama"].live_checked is True
        assert statuses["ollama"].reachable is True

    def test_connection_error_reports_unreachable(self):
        router = ModelRouter()
        with _patched_async_client(side_effect=httpx.ConnectError("refused")):
            statuses = {s.provider: s for s in _run(check_providers(router, live=True))}
        assert statuses["ollama"].reachable is False


class TestLiveCheckUnsupportedProviders:
    """anthropic/bedrock aren't OpenAI-compatible, so they never make a live
    call — but check_providers() still probes ollama (always "configured")
    on every live=True run, so httpx is mocked here too, purely to keep that
    incidental ollama probe from making a real network call."""

    def test_anthropic_reports_not_supported(self):
        router = ModelRouter(anthropic_api_key="sk-test")
        with _patched_async_client(response=_mock_response(200)):
            statuses = {s.provider: s for s in _run(check_providers(router, live=True))}
        assert statuses["anthropic"].live_checked is False
        assert statuses["anthropic"].reachable is None
        assert "not supported" in statuses["anthropic"].detail.lower()

    def test_bedrock_reports_not_supported(self):
        router = ModelRouter()
        with _patched_async_client(response=_mock_response(200)):
            statuses = {s.provider: s for s in _run(check_providers(router, live=True))}
        assert statuses["bedrock"].live_checked is False


class TestProviderStatusToDict:
    def test_to_dict_has_expected_keys(self):
        status = ProviderStatus(
            provider="openai", configured=True, live_checked=False, reachable=None, detail=""
        )
        assert status.to_dict() == {
            "provider": "openai", "configured": True, "live_checked": False,
            "reachable": None, "detail": "",
        }


def _run(coro):
    import asyncio

    return asyncio.run(coro)

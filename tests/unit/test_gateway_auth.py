"""Tests for the optional X-API-Key gateway authentication middleware.

When gateway.api_key is non-empty in the config, the middleware enforces
it on all /api/* requests. When it is empty (the default), auth is
disabled and every request passes through unchanged.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cortexflow_ai.config import CortexFlowConfig, GatewayConfig
from cortexflow_ai.gateway.main import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(api_key: str = "") -> TestClient:
    cfg = CortexFlowConfig(gateway=GatewayConfig(api_key=api_key))
    app = create_app(cfg)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Auth disabled (api_key == "")
# ---------------------------------------------------------------------------


class TestAuthDisabled:
    def test_status_passes_without_header(self):
        client = _make_client(api_key="")
        r = client.get("/api/v1/status")
        assert r.status_code == 200

    def test_status_passes_with_arbitrary_header(self):
        client = _make_client(api_key="")
        r = client.get("/api/v1/status", headers={"X-API-Key": "whatever"})
        assert r.status_code == 200

    def test_health_passes_without_header(self):
        client = _make_client(api_key="")
        r = client.get("/health")
        assert r.status_code == 200

    def test_metrics_snapshot_passes_without_header(self):
        client = _make_client(api_key="")
        r = client.get("/api/v1/metrics/snapshot")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Auth enabled — correct key
# ---------------------------------------------------------------------------


class TestAuthEnabledCorrectKey:
    KEY = "super-secret-token-42"

    def test_status_with_correct_key(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/api/v1/status", headers={"X-API-Key": self.KEY})
        assert r.status_code == 200

    def test_metrics_snapshot_with_correct_key(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/api/v1/metrics/snapshot", headers={"X-API-Key": self.KEY})
        assert r.status_code == 200

    def test_hub_packages_with_correct_key(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/api/v1/hub/packages", headers={"X-API-Key": self.KEY})
        assert r.status_code == 200

    def test_orchestrator_status_with_correct_key(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/api/v1/orchestrator/status", headers={"X-API-Key": self.KEY})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Auth enabled — missing or wrong key
# ---------------------------------------------------------------------------


class TestAuthEnabledMissingOrWrongKey:
    KEY = "secret-key-xyz"

    def test_status_missing_key_returns_401(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/api/v1/status")
        assert r.status_code == 401

    def test_status_wrong_key_returns_401(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/api/v1/status", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401

    def test_metrics_missing_key_returns_401(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/api/v1/metrics")
        assert r.status_code == 401

    def test_hub_packages_missing_key_returns_401(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/api/v1/hub/packages")
        assert r.status_code == 401

    def test_error_body_contains_detail_field(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/api/v1/status")
        assert "detail" in r.json()

    def test_error_body_detail_is_unauthorized(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/api/v1/status")
        assert r.json()["detail"] == "Unauthorized"

    def test_empty_string_key_header_returns_401(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/api/v1/status", headers={"X-API-Key": ""})
        assert r.status_code == 401

    def test_case_sensitive_key_check(self):
        client = _make_client(api_key="CaseSensitive")
        r = client.get("/api/v1/status", headers={"X-API-Key": "casesensitive"})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Auth enabled — exempt routes
# ---------------------------------------------------------------------------


class TestAuthExemptRoutes:
    KEY = "only-on-api-routes"

    def test_health_exempt_no_key(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_exempt_wrong_key_still_passes(self):
        client = _make_client(api_key=self.KEY)
        r = client.get("/health", headers={"X-API-Key": "nonsense"})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Config: api_key loaded from config dict
# ---------------------------------------------------------------------------


class TestApiKeyFromConfig:
    def test_api_key_parsed_from_gateway_section(self):
        from cortexflow_ai.config import _parse_config

        cfg = _parse_config({"gateway": {"api_key": "from-config-file"}})
        assert cfg.gateway.api_key == "from-config-file"

    def test_api_key_default_is_empty(self):
        from cortexflow_ai.config import _parse_config

        cfg = _parse_config({})
        assert cfg.gateway.api_key == ""

    def test_api_key_resolves_env_secret(self, monkeypatch: pytest.MonkeyPatch):
        from cortexflow_ai.config import _parse_config

        monkeypatch.setenv("CF_API_KEY", "env-resolved-key")
        cfg = _parse_config({"gateway": {"api_key": "ENV:CF_API_KEY"}})
        assert cfg.gateway.api_key == "env-resolved-key"

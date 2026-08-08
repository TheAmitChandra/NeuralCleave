"""Tests for GET and DELETE /api/v1/privacy/report gateway endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from neuralcleave.privacy.audit import AUDIT_LOG


@pytest.fixture(autouse=True)
def _clear_audit_log():
    """Clear the audit log before and after every test."""
    AUDIT_LOG.clear_all()
    yield
    AUDIT_LOG.clear_all()


@pytest.fixture()
def client() -> TestClient:
    from neuralcleave.gateway.main import create_app

    return TestClient(create_app())


class TestPrivacyReportGet:
    def test_get_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/v1/privacy/report")
        assert resp.status_code == 200

    def test_get_empty_log_returns_zero_total(self, client: TestClient) -> None:
        resp = client.get("/api/v1/privacy/report")
        data = resp.json()
        assert data["total"] == 0
        assert data["entries"] == []

    def test_get_returns_recorded_entries(self, client: TestClient) -> None:
        AUDIT_LOG.record(session_id="s1", method="GET", url="https://api.openai.com/v1/chat")
        AUDIT_LOG.record(session_id="s1", method="POST", url="https://api.anthropic.com/messages")

        resp = client.get("/api/v1/privacy/report")
        data = resp.json()
        assert data["total"] == 2

    def test_get_with_session_filter_returns_only_matching(self, client: TestClient) -> None:
        AUDIT_LOG.record(session_id="a", method="GET", url="https://openai.com")
        AUDIT_LOG.record(session_id="b", method="GET", url="https://anthropic.com")

        resp = client.get("/api/v1/privacy/report?session_id=a")
        data = resp.json()
        assert data["total"] == 1
        assert data["session_id"] == "a"
        assert data["entries"][0]["session_id"] == "a"

    def test_get_unique_destinations_listed(self, client: TestClient) -> None:
        AUDIT_LOG.record(session_id="s", method="GET", url="https://api.openai.com/v1/a")
        AUDIT_LOG.record(session_id="s", method="GET", url="https://api.openai.com/v1/b")

        resp = client.get("/api/v1/privacy/report")
        data = resp.json()
        assert data["unique_destinations"] == ["api.openai.com"]


class TestPrivacyReportDelete:
    def test_delete_all_returns_cleared_count(self, client: TestClient) -> None:
        AUDIT_LOG.record(session_id="s1", method="GET", url="https://a.com")
        AUDIT_LOG.record(session_id="s2", method="GET", url="https://b.com")

        resp = client.delete("/api/v1/privacy/report")
        data = resp.json()
        assert resp.status_code == 200
        assert data["cleared"] == 2

    def test_delete_all_leaves_log_empty(self, client: TestClient) -> None:
        AUDIT_LOG.record(session_id="s", method="GET", url="https://x.com")
        client.delete("/api/v1/privacy/report")
        assert len(AUDIT_LOG) == 0

    def test_delete_by_session_only_removes_matching(self, client: TestClient) -> None:
        AUDIT_LOG.record(session_id="a", method="GET", url="https://a.com")
        AUDIT_LOG.record(session_id="b", method="GET", url="https://b.com")

        resp = client.delete("/api/v1/privacy/report?session_id=a")
        data = resp.json()
        assert data["cleared"] == 1
        assert data["session_id"] == "a"
        assert len(AUDIT_LOG) == 1  # session "b" still present

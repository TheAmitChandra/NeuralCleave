"""Tests for PrivacyAuditLog in neuralcleave.privacy.audit."""

from __future__ import annotations

import time

import pytest

from neuralcleave.privacy.audit import AuditEntry, PrivacyAuditLog


@pytest.fixture()
def log() -> PrivacyAuditLog:
    """Fresh audit log for each test."""
    return PrivacyAuditLog()


class TestAuditEntryCreation:
    def test_record_returns_audit_entry(self, log: PrivacyAuditLog) -> None:
        entry = log.record(session_id="s1", method="GET", url="https://api.openai.com/v1/models")
        assert isinstance(entry, AuditEntry)

    def test_record_normalises_method_to_uppercase(self, log: PrivacyAuditLog) -> None:
        entry = log.record(session_id="s1", method="post", url="https://example.com/endpoint")
        assert entry.method == "POST"

    def test_record_extracts_destination_from_url(self, log: PrivacyAuditLog) -> None:
        entry = log.record(session_id="s1", method="GET", url="https://api.openai.com/v1/models")
        assert entry.destination == "api.openai.com"

    def test_record_sets_timestamp_close_to_now(self, log: PrivacyAuditLog) -> None:
        before = time.time()
        entry = log.record(session_id="s1", method="GET", url="https://example.com")
        after = time.time()
        assert before <= entry.timestamp <= after

    def test_to_dict_includes_all_fields(self, log: PrivacyAuditLog) -> None:
        entry = log.record(session_id="s1", method="GET", url="https://example.com/path")
        d = entry.to_dict()
        assert d["session_id"] == "s1"
        assert d["method"] == "GET"
        assert d["url"] == "https://example.com/path"
        assert "destination" in d
        assert "timestamp" in d


class TestEntryQuerying:
    def test_entries_for_session_returns_only_matching(self, log: PrivacyAuditLog) -> None:
        log.record(session_id="a", method="GET", url="https://a.com")
        log.record(session_id="b", method="GET", url="https://b.com")
        log.record(session_id="a", method="POST", url="https://a.com/post")

        entries = log.entries_for_session("a")
        assert len(entries) == 2
        assert all(e.session_id == "a" for e in entries)

    def test_entries_for_session_empty_when_no_match(self, log: PrivacyAuditLog) -> None:
        log.record(session_id="a", method="GET", url="https://a.com")
        assert log.entries_for_session("z") == []

    def test_all_entries_returns_everything(self, log: PrivacyAuditLog) -> None:
        log.record(session_id="a", method="GET", url="https://a.com")
        log.record(session_id="b", method="POST", url="https://b.com")
        assert len(log.all_entries()) == 2

    def test_len_reflects_total_entries(self, log: PrivacyAuditLog) -> None:
        assert len(log) == 0
        log.record(session_id="s", method="GET", url="https://x.com")
        assert len(log) == 1
        log.record(session_id="s", method="GET", url="https://y.com")
        assert len(log) == 2


class TestUniqueDestinations:
    def test_unique_destinations_deduplicates_host(self, log: PrivacyAuditLog) -> None:
        log.record(session_id="s", method="GET", url="https://api.openai.com/v1/a")
        log.record(session_id="s", method="POST", url="https://api.openai.com/v1/b")
        dests = log.unique_destinations("s")
        assert dests == ["api.openai.com"]

    def test_unique_destinations_across_sessions(self, log: PrivacyAuditLog) -> None:
        log.record(session_id="a", method="GET", url="https://host-a.com")
        log.record(session_id="b", method="GET", url="https://host-b.com")
        dests = log.unique_destinations()
        assert set(dests) == {"host-a.com", "host-b.com"}


class TestClearing:
    def test_clear_session_removes_only_matching_entries(self, log: PrivacyAuditLog) -> None:
        log.record(session_id="a", method="GET", url="https://a.com")
        log.record(session_id="b", method="GET", url="https://b.com")
        removed = log.clear_session("a")
        assert removed == 1
        assert len(log) == 1
        assert log.entries_for_session("a") == []

    def test_clear_all_removes_every_entry(self, log: PrivacyAuditLog) -> None:
        log.record(session_id="a", method="GET", url="https://a.com")
        log.record(session_id="b", method="GET", url="https://b.com")
        removed = log.clear_all()
        assert removed == 2
        assert len(log) == 0

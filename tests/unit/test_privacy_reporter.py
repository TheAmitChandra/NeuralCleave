"""Tests for neuralcleave.privacy.reporter formatting functions."""

from __future__ import annotations

import pytest

from neuralcleave.privacy.audit import AuditEntry, PrivacyAuditLog
from neuralcleave.privacy.reporter import format_json_report, format_text_report


@pytest.fixture()
def log() -> PrivacyAuditLog:
    return PrivacyAuditLog()


def _entry(session: str, url: str, method: str = "GET") -> AuditEntry:
    log = PrivacyAuditLog()
    return log.record(session_id=session, method=method, url=url)


class TestFormatTextReport:
    def test_empty_entries_returns_no_calls_message(self) -> None:
        text = format_text_report([])
        assert "No outbound HTTP calls" in text

    def test_session_id_appears_in_header(self) -> None:
        text = format_text_report([], session_id="abc-123")
        assert "abc-123" in text

    def test_destinations_listed_in_report(self) -> None:
        entries = [
            _entry("s", "https://api.openai.com/v1/chat"),
            _entry("s", "https://api.anthropic.com/v1/messages"),
        ]
        text = format_text_report(entries)
        assert "api.openai.com" in text
        assert "api.anthropic.com" in text

    def test_total_call_count_shown(self) -> None:
        entries = [_entry("s", "https://x.com"), _entry("s", "https://y.com")]
        text = format_text_report(entries)
        assert "Total calls: 2" in text

    def test_method_and_url_shown_per_entry(self) -> None:
        entries = [_entry("s", "https://example.com/endpoint", method="POST")]
        text = format_text_report(entries)
        assert "POST" in text
        assert "https://example.com/endpoint" in text

    def test_duplicate_destinations_deduplicated(self) -> None:
        entries = [
            _entry("s", "https://api.openai.com/v1/a"),
            _entry("s", "https://api.openai.com/v1/b"),
        ]
        text = format_text_report(entries)
        assert text.count("api.openai.com") >= 1
        assert "Destinations contacted: 1" in text


class TestFormatJsonReport:
    def test_json_report_has_expected_keys(self) -> None:
        data = format_json_report([])
        assert "session_id" in data
        assert "total" in data
        assert "unique_destinations" in data
        assert "entries" in data

    def test_total_reflects_entry_count(self) -> None:
        entries = [_entry("s", "https://x.com"), _entry("s", "https://y.com")]
        data = format_json_report(entries, session_id="s")
        assert data["total"] == 2

    def test_session_id_propagated(self) -> None:
        data = format_json_report([], session_id="my-session")
        assert data["session_id"] == "my-session"

    def test_entries_are_serialisable_dicts(self) -> None:
        entries = [_entry("s", "https://openai.com/api")]
        data = format_json_report(entries)
        assert isinstance(data["entries"][0], dict)
        assert "url" in data["entries"][0]

    def test_unique_destinations_list_deduplicates(self) -> None:
        entries = [
            _entry("s", "https://same.host/a"),
            _entry("s", "https://same.host/b"),
        ]
        data = format_json_report(entries)
        assert data["unique_destinations"] == ["same.host"]

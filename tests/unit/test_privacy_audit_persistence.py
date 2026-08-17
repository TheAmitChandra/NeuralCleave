"""Tests for PrivacyAuditLog's SQLite persistence (P0 of the 2026-08-17 gap analysis).

Before this, PrivacyAuditLog was in-memory only and reset on every restart —
see test_privacy_audit.py for the pre-existing in-memory behaviour, which
these tests don't repeat. These tests cover the new ``db_path``/
``retention_days`` opt-in persistence path specifically.
"""

from __future__ import annotations

import time

from neuralcleave.privacy.audit import (
    DEFAULT_RETENTION_DAYS,
    PrivacyAuditLog,
)


class TestInMemoryDefaultUnaffected:
    def test_no_db_path_creates_no_file(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        log = PrivacyAuditLog()
        log.record(session_id="s", method="GET", url="https://x.com")
        assert list(tmp_path.iterdir()) == []

    def test_no_db_path_leaves_db_attribute_none(self) -> None:
        log = PrivacyAuditLog()
        assert log._db is None


class TestPersistenceAcrossReopen:
    def test_entries_survive_reopening_the_same_db_path(self, tmp_path) -> None:
        db_path = tmp_path / "audit.db"
        log1 = PrivacyAuditLog(db_path=str(db_path))
        log1.record(session_id="s", method="GET", url="https://api.example.com/x")
        log1.close()

        log2 = PrivacyAuditLog(db_path=str(db_path))
        entries = log2.entries_for_session("s")
        assert len(entries) == 1
        assert entries[0].url == "https://api.example.com/x"

    def test_clear_session_persists_across_reopen(self, tmp_path) -> None:
        db_path = tmp_path / "audit.db"
        log1 = PrivacyAuditLog(db_path=str(db_path))
        log1.record(session_id="a", method="GET", url="https://a.com")
        log1.record(session_id="b", method="GET", url="https://b.com")
        log1.clear_session("a")
        log1.close()

        log2 = PrivacyAuditLog(db_path=str(db_path))
        assert log2.entries_for_session("a") == []
        assert len(log2.entries_for_session("b")) == 1

    def test_clear_all_persists_across_reopen(self, tmp_path) -> None:
        db_path = tmp_path / "audit.db"
        log1 = PrivacyAuditLog(db_path=str(db_path))
        log1.record(session_id="a", method="GET", url="https://a.com")
        log1.clear_all()
        log1.close()

        log2 = PrivacyAuditLog(db_path=str(db_path))
        assert log2.all_entries() == []

    def test_creates_parent_directory_if_missing(self, tmp_path) -> None:
        db_path = tmp_path / "nested" / "dir" / "audit.db"
        log = PrivacyAuditLog(db_path=str(db_path))
        log.record(session_id="s", method="GET", url="https://x.com")
        assert db_path.exists()

    def test_expands_user_home_shorthand(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        log = PrivacyAuditLog(db_path="~/audit-home-test.db")
        log.record(session_id="s", method="GET", url="https://x.com")
        assert (tmp_path / "audit-home-test.db").exists()


class TestRetentionPruning:
    def test_default_retention_is_90_days(self) -> None:
        assert DEFAULT_RETENTION_DAYS == 90

    def test_old_entry_pruned_on_next_record(self, tmp_path) -> None:
        db_path = tmp_path / "audit.db"
        log = PrivacyAuditLog(db_path=str(db_path), retention_days=1)
        old_ts = time.time() - 2 * 86400
        log._db.execute(
            "INSERT INTO audit_entries (session_id, method, url, destination, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s", "GET", "https://old.example.com", "old.example.com", old_ts),
        )
        log._db.commit()

        log.record(session_id="s", method="GET", url="https://new.example.com")

        entries = log.entries_for_session("s")
        assert len(entries) == 1
        assert entries[0].destination == "new.example.com"

    def test_old_entry_pruned_on_load(self, tmp_path) -> None:
        db_path = tmp_path / "audit.db"
        setup_log = PrivacyAuditLog(db_path=str(db_path), retention_days=90)
        old_ts = time.time() - 2 * 86400
        setup_log._db.execute(
            "INSERT INTO audit_entries (session_id, method, url, destination, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s", "GET", "https://old.example.com", "old.example.com", old_ts),
        )
        setup_log._db.commit()
        setup_log.close()

        reopened = PrivacyAuditLog(db_path=str(db_path), retention_days=1)
        assert reopened.entries_for_session("s") == []

    def test_prune_expired_manual_call_removes_old_entries(self, tmp_path) -> None:
        db_path = tmp_path / "audit.db"
        log = PrivacyAuditLog(db_path=str(db_path), retention_days=1)
        entry = log.record(session_id="s", method="GET", url="https://x.com")

        old_ts = time.time() - 2 * 86400
        log._db.execute(
            "UPDATE audit_entries SET timestamp = ? WHERE session_id = ?", (old_ts, "s")
        )
        log._db.commit()
        entry.timestamp = old_ts  # same object instance held in log._entries

        removed = log.prune_expired()
        assert removed == 1
        assert log.entries_for_session("s") == []

    def test_prune_expired_returns_zero_when_persistence_disabled(self) -> None:
        log = PrivacyAuditLog()
        log.record(session_id="s", method="GET", url="https://x.com")
        assert log.prune_expired() == 0
        assert len(log) == 1

    def test_recent_entries_survive_pruning(self, tmp_path) -> None:
        db_path = tmp_path / "audit.db"
        log = PrivacyAuditLog(db_path=str(db_path), retention_days=90)
        log.record(session_id="s", method="GET", url="https://fresh.example.com")
        assert len(log.entries_for_session("s")) == 1


class TestConnectionLifecycle:
    def test_close_clears_internal_connection_reference(self, tmp_path) -> None:
        db_path = tmp_path / "audit.db"
        log = PrivacyAuditLog(db_path=str(db_path))
        assert log._db is not None
        log.close()
        assert log._db is None

    def test_close_on_in_memory_only_log_is_a_no_op(self) -> None:
        log = PrivacyAuditLog()
        log.close()  # must not raise
        assert log._db is None

    def test_record_after_close_still_works_in_memory_only(self, tmp_path) -> None:
        db_path = tmp_path / "audit.db"
        log = PrivacyAuditLog(db_path=str(db_path))
        log.close()

        entry = log.record(session_id="s", method="GET", url="https://x.com")

        assert entry.url == "https://x.com"
        assert len(log) == 1


class TestModuleSingleton:
    def test_audit_log_singleton_has_persistence_enabled(self) -> None:
        """Regression guard: proves AUDIT_LOG isn't silently falling back to
        in-memory-only. The test session routes it to sqlite ':memory:' via
        tests/conftest.py rather than disabling persistence outright."""
        from neuralcleave.privacy.audit import AUDIT_LOG

        assert AUDIT_LOG._db is not None

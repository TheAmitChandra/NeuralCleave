"""Tests for AuditEvent and AuditTrail."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.observability.audit_trail import AuditEvent, AuditOutcome, AuditTrail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_trail() -> AuditTrail:
    return AuditTrail()


def populate(trail: AuditTrail) -> None:
    trail.record("user:alice", "deploy", "service:backend", "allowed")
    trail.record("user:bob", "delete", "service:redis", "denied")
    trail.record("user:alice", "approve", "workflow:123", "pending")
    trail.record("user:carol", "read", "service:backend", "allowed")


# ===========================================================================
# TestAuditOutcome
# ===========================================================================


class TestAuditOutcome:
    def test_values(self) -> None:
        assert AuditOutcome.ALLOWED == "allowed"
        assert AuditOutcome.DENIED == "denied"
        assert AuditOutcome.PENDING == "pending"


# ===========================================================================
# TestAuditEvent
# ===========================================================================


class TestAuditEvent:
    def test_immutable(self) -> None:
        e = AuditEvent(
            event_id="abc",
            actor_id="user:x",
            action="read",
            resource="res:y",
            outcome="allowed",
            timestamp=datetime.now(tz=timezone.utc),
        )
        with pytest.raises((AttributeError, TypeError)):
            e.outcome = "denied"  # type: ignore[misc]

    def test_to_dict_keys(self) -> None:
        e = AuditEvent(
            event_id="abc",
            actor_id="user:x",
            action="read",
            resource="res:y",
            outcome="denied",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            metadata={"reason": "policy"},
        )
        d = e.to_dict()
        assert d["event_id"] == "abc"
        assert d["outcome"] == "denied"
        assert d["metadata"]["reason"] == "policy"
        assert "timestamp" in d

    def test_to_dict_metadata_copy(self) -> None:
        meta = {"k": "v"}
        e = AuditEvent("id", "a", "b", "c", "allowed", datetime.now(tz=timezone.utc), metadata=meta)
        e.to_dict()["metadata"]["k"] = "changed"
        assert meta["k"] == "v"  # original unaffected


# ===========================================================================
# TestAuditTrailRecord
# ===========================================================================


class TestAuditTrailRecord:
    def test_record_returns_event(self) -> None:
        t = make_trail()
        e = t.record("user:alice", "read", "res:x", "allowed")
        assert isinstance(e, AuditEvent)
        assert e.actor_id == "user:alice"
        assert e.outcome == "allowed"

    def test_event_id_is_unique(self) -> None:
        t = make_trail()
        ids = {t.record("u", "a", "r", "allowed").event_id for _ in range(20)}
        assert len(ids) == 20

    def test_invalid_outcome_raises(self) -> None:
        t = make_trail()
        with pytest.raises(ValueError, match="outcome"):
            t.record("u", "a", "r", "unknown")

    def test_empty_actor_raises(self) -> None:
        t = make_trail()
        with pytest.raises(ValueError, match="actor_id"):
            t.record("", "a", "r", "allowed")

    def test_empty_action_raises(self) -> None:
        t = make_trail()
        with pytest.raises(ValueError, match="action"):
            t.record("u", "", "r", "allowed")

    def test_empty_resource_raises(self) -> None:
        t = make_trail()
        with pytest.raises(ValueError, match="resource"):
            t.record("u", "a", "", "allowed")

    def test_metadata_stored(self) -> None:
        t = make_trail()
        e = t.record("u", "a", "r", "denied", metadata={"ip": "1.2.3.4"})
        assert e.metadata["ip"] == "1.2.3.4"

    def test_custom_timestamp(self) -> None:
        t = make_trail()
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        e = t.record("u", "a", "r", "allowed", timestamp=ts)
        assert e.timestamp == ts

    def test_default_timestamp_is_utc(self) -> None:
        t = make_trail()
        e = t.record("u", "a", "r", "allowed")
        assert e.timestamp.tzinfo is not None


# ===========================================================================
# TestAuditTrailQuery
# ===========================================================================


class TestAuditTrailQuery:
    def test_get_events_all(self) -> None:
        t = make_trail()
        populate(t)
        assert len(t.get_events()) == 4

    def test_filter_by_actor(self) -> None:
        t = make_trail()
        populate(t)
        events = t.get_events(actor_id="user:alice")
        assert len(events) == 2
        assert all(e.actor_id == "user:alice" for e in events)

    def test_filter_by_outcome(self) -> None:
        t = make_trail()
        populate(t)
        denied = t.get_events(outcome="denied")
        assert len(denied) == 1
        assert denied[0].actor_id == "user:bob"

    def test_filter_by_action(self) -> None:
        t = make_trail()
        populate(t)
        assert len(t.get_events(action="deploy")) == 1

    def test_filter_by_resource(self) -> None:
        t = make_trail()
        populate(t)
        events = t.get_events(resource="service:backend")
        assert len(events) == 2

    def test_multi_filter(self) -> None:
        t = make_trail()
        populate(t)
        events = t.get_events(actor_id="user:alice", outcome="allowed")
        assert len(events) == 1
        assert events[0].action == "deploy"

    def test_get_event_by_id(self) -> None:
        t = make_trail()
        e = t.record("u", "a", "r", "pending")
        found = t.get_event(e.event_id)
        assert found is e

    def test_get_event_missing(self) -> None:
        t = make_trail()
        assert t.get_event("nonexistent") is None

    def test_events_order_oldest_first(self) -> None:
        t = make_trail()
        populate(t)
        events = t.get_events()
        actions = [e.action for e in events]
        assert actions[0] == "deploy"


# ===========================================================================
# TestAuditTrailSummary
# ===========================================================================


class TestAuditTrailSummary:
    def test_event_count(self) -> None:
        t = make_trail()
        populate(t)
        assert t.event_count == 4

    def test_event_count_empty(self) -> None:
        assert make_trail().event_count == 0

    def test_outcome_counts(self) -> None:
        t = make_trail()
        populate(t)
        counts = t.outcome_counts()
        assert counts["allowed"] == 2
        assert counts["denied"] == 1
        assert counts["pending"] == 1

    def test_actors(self) -> None:
        t = make_trail()
        populate(t)
        assert t.actors() == ["user:alice", "user:bob", "user:carol"]


# ===========================================================================
# TestAuditTrailMaintenance
# ===========================================================================


class TestAuditTrailMaintenance:
    def test_clear(self) -> None:
        t = make_trail()
        populate(t)
        t.clear()
        assert t.event_count == 0

    def test_max_events_evicts_oldest(self) -> None:
        t = AuditTrail(max_events=3)
        t.record("u", "a", "r1", "allowed")
        t.record("u", "a", "r2", "allowed")
        t.record("u", "a", "r3", "allowed")
        t.record("u", "a", "r4", "allowed")  # evicts r1
        events = t.get_events()
        assert len(events) == 3
        assert events[0].resource == "r2"

    def test_negative_max_events_raises(self) -> None:
        with pytest.raises(ValueError, match="max_events"):
            AuditTrail(max_events=-1)

    def test_unlimited_max_events(self) -> None:
        t = AuditTrail(max_events=0)
        for i in range(100):
            t.record("u", "a", f"r{i}", "allowed")
        assert t.event_count == 100

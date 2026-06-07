"""
Unit tests for AgentCommunicationBus and BusEvent.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.events.bus import AgentCommunicationBus, BusEvent

# ---------------------------------------------------------------------------
# BusEvent
# ---------------------------------------------------------------------------


class TestBusEvent:
    def test_to_dict_has_required_keys(self):
        from datetime import timezone

        event = BusEvent(
            event_id="ev-001",
            topic="agent.task",
            payload={"data": 42},
            publisher_id="planner",
        )
        d = event.to_dict()
        assert d["event_id"] == "ev-001"
        assert d["topic"] == "agent.task"
        assert d["payload"] == {"data": 42}
        assert d["publisher_id"] == "planner"
        assert "timestamp" in d

    def test_timestamp_iso_format(self):
        event = BusEvent(event_id="x", topic="t", payload={}, publisher_id="p")
        ts = event.to_dict()["timestamp"]
        datetime.fromisoformat(ts)  # must not raise

    def test_payload_preserved(self):
        event = BusEvent(event_id="x", topic="t", payload={"nested": {"a": 1}}, publisher_id="p")
        assert event.to_dict()["payload"]["nested"]["a"] == 1

    def test_event_id_in_dict(self):
        event = BusEvent(event_id="abc", topic="x", payload={}, publisher_id="q")
        assert event.to_dict()["event_id"] == "abc"


# ---------------------------------------------------------------------------
# AgentCommunicationBus — construction
# ---------------------------------------------------------------------------


class TestBusInit:
    def test_initial_state(self):
        bus = AgentCommunicationBus()
        assert bus.event_count == 0
        assert bus.topics == []

    def test_subscriber_count_unknown_topic(self):
        bus = AgentCommunicationBus()
        assert bus.subscriber_count("no-such-topic") == 0


# ---------------------------------------------------------------------------
# Subscribe / unsubscribe
# ---------------------------------------------------------------------------


class TestSubscription:
    def test_subscribe_adds_handler(self):
        bus = AgentCommunicationBus()

        async def h(e):
            pass

        bus.subscribe("task.done", h)
        assert bus.subscriber_count("task.done") == 1

    def test_subscribe_multiple_handlers(self):
        bus = AgentCommunicationBus()

        async def h1(e):
            pass

        async def h2(e):
            pass

        bus.subscribe("t", h1)
        bus.subscribe("t", h2)
        assert bus.subscriber_count("t") == 2

    def test_subscribe_duplicate_ignored(self):
        bus = AgentCommunicationBus()

        async def h(e):
            pass

        bus.subscribe("t", h)
        bus.subscribe("t", h)
        assert bus.subscriber_count("t") == 1

    def test_subscribe_non_callable_raises(self):
        bus = AgentCommunicationBus()
        with pytest.raises(TypeError):
            bus.subscribe("t", "not-a-function")  # type: ignore

    def test_unsubscribe_removes_handler(self):
        bus = AgentCommunicationBus()

        async def h(e):
            pass

        bus.subscribe("t", h)
        bus.unsubscribe("t", h)
        assert bus.subscriber_count("t") == 0

    def test_unsubscribe_non_subscribed_is_silent(self):
        bus = AgentCommunicationBus()

        async def h(e):
            pass

        bus.unsubscribe("t", h)  # should not raise

    def test_topics_reflects_active_subscriptions(self):
        bus = AgentCommunicationBus()

        async def h(e):
            pass

        bus.subscribe("topic-a", h)
        bus.subscribe("topic-b", h)
        assert set(bus.topics) == {"topic-a", "topic-b"}

    def test_topics_excludes_empty_subscriber_lists(self):
        bus = AgentCommunicationBus()

        async def h(e):
            pass

        bus.subscribe("t", h)
        bus.unsubscribe("t", h)
        assert "t" not in bus.topics


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


class TestPublish:
    async def test_publish_returns_bus_event(self):
        bus = AgentCommunicationBus()
        event = await bus.publish("task.done", {"result": "ok"}, publisher_id="executor")
        assert isinstance(event, BusEvent)

    async def test_publish_assigns_unique_event_id(self):
        bus = AgentCommunicationBus()
        e1 = await bus.publish("t", {}, publisher_id="a")
        e2 = await bus.publish("t", {}, publisher_id="a")
        assert e1.event_id != e2.event_id

    async def test_publish_stores_event_in_history(self):
        bus = AgentCommunicationBus()
        await bus.publish("t", {}, publisher_id="a")
        assert bus.event_count == 1

    async def test_publish_empty_topic_raises(self):
        bus = AgentCommunicationBus()
        with pytest.raises(ValueError, match="topic"):
            await bus.publish("", {}, publisher_id="a")

    async def test_publish_calls_subscribed_handler(self):
        bus = AgentCommunicationBus()
        received: list[BusEvent] = []

        async def h(event: BusEvent):
            received.append(event)

        bus.subscribe("task.done", h)
        await bus.publish("task.done", {"x": 1}, publisher_id="planner")
        assert len(received) == 1
        assert received[0].payload == {"x": 1}

    async def test_publish_calls_multiple_handlers(self):
        bus = AgentCommunicationBus()
        calls: list[str] = []

        async def h1(e):
            calls.append("h1")

        async def h2(e):
            calls.append("h2")

        bus.subscribe("t", h1)
        bus.subscribe("t", h2)
        await bus.publish("t", {}, publisher_id="a")
        assert "h1" in calls
        assert "h2" in calls

    async def test_publish_does_not_call_other_topic_handlers(self):
        bus = AgentCommunicationBus()
        received: list[BusEvent] = []

        async def h(e):
            received.append(e)

        bus.subscribe("other.topic", h)
        await bus.publish("task.done", {}, publisher_id="a")
        assert len(received) == 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    async def test_dispatch_returns_handler_count(self):
        bus = AgentCommunicationBus()

        async def h1(e):
            pass

        async def h2(e):
            pass

        bus.subscribe("t", h1)
        bus.subscribe("t", h2)

        event = BusEvent(event_id="x", topic="t", payload={}, publisher_id="a")
        count = await bus.dispatch(event)
        assert count == 2

    async def test_dispatch_no_subscribers_returns_zero(self):
        bus = AgentCommunicationBus()
        event = BusEvent(event_id="x", topic="empty", payload={}, publisher_id="a")
        count = await bus.dispatch(event)
        assert count == 0


# ---------------------------------------------------------------------------
# History / introspection
# ---------------------------------------------------------------------------


class TestHistory:
    async def test_get_events_all(self):
        bus = AgentCommunicationBus()
        await bus.publish("a", {}, publisher_id="p")
        await bus.publish("b", {}, publisher_id="p")
        assert len(bus.get_events()) == 2

    async def test_get_events_filtered_by_topic(self):
        bus = AgentCommunicationBus()
        await bus.publish("task.done", {}, publisher_id="p")
        await bus.publish("task.failed", {}, publisher_id="p")
        await bus.publish("task.done", {}, publisher_id="p")
        done_events = bus.get_events("task.done")
        assert len(done_events) == 2
        assert all(e.topic == "task.done" for e in done_events)

    async def test_clear_history(self):
        bus = AgentCommunicationBus()
        await bus.publish("t", {}, publisher_id="p")
        bus.clear_history()
        assert bus.event_count == 0

    async def test_event_count_increments(self):
        bus = AgentCommunicationBus()
        for _ in range(5):
            await bus.publish("t", {}, publisher_id="p")
        assert bus.event_count == 5

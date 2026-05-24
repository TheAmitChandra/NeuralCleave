"""Unit tests for SDK extension modules — memory_sdk.py and event_sdk.py."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.sdk.memory_sdk import MemoryBackendSDK, MemoryRecord, MemoryRegistry
from app.sdk.event_sdk import EventSDK, TriggerSDK, on_event
from app.core.events.bus import BusEvent


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(autouse=True)
def clear_memory_registry():
    """Ensure MemoryRegistry is empty before and after every test."""
    MemoryRegistry._registry.clear()
    yield
    MemoryRegistry._registry.clear()


@pytest.fixture(autouse=True)
def reset_event_sdk_bus():
    """Give EventSDK a fresh bus for every test."""
    from app.core.events.bus import AgentCommunicationBus

    EventSDK._bus = AgentCommunicationBus()
    yield
    EventSDK._bus = AgentCommunicationBus()


# ---------------------------------------------------------------------------
# Concrete memory backend for testing
# ---------------------------------------------------------------------------


class InMemoryBackend(MemoryBackendSDK):
    tier = "in_memory"
    priority = 10

    def __init__(self) -> None:
        self._store: dict[str, MemoryRecord] = {}

    async def store(self, record: MemoryRecord) -> None:
        key = record.memory_id or "default"
        self._store[key] = record

    async def retrieve(
        self,
        query: str,
        *,
        agent_id: str,
        top_k: int = 5,
    ) -> list[MemoryRecord]:
        results = [
            r for r in self._store.values() if query.lower() in str(r.content).lower()
        ]
        return sorted(results, key=lambda r: r.score, reverse=True)[:top_k]

    async def delete(self, memory_id: str) -> None:
        self._store.pop(memory_id, None)


# ---------------------------------------------------------------------------
# Concrete trigger for testing
# ---------------------------------------------------------------------------


class MockTrigger(TriggerSDK):
    source_name = "test.trigger"

    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


# ===========================================================================
# MemoryRecord tests
# ===========================================================================


class TestMemoryRecord:
    def test_defaults(self):
        r = MemoryRecord(content="hello")
        assert r.content == "hello"
        assert r.memory_id == ""
        assert r.score == 1.0
        assert r.metadata == {}

    def test_source_property_from_metadata(self):
        r = MemoryRecord(content="x", metadata={"source": "episodic"})
        assert r.source == "episodic"

    def test_source_property_default(self):
        r = MemoryRecord(content="y")
        assert r.source == "unknown"

    def test_custom_fields(self):
        r = MemoryRecord(
            content={"key": "value"},
            memory_id="abc-123",
            score=0.75,
            metadata={"agent_id": "agent-1"},
        )
        assert r.memory_id == "abc-123"
        assert r.score == 0.75
        assert r.metadata["agent_id"] == "agent-1"


# ===========================================================================
# MemoryBackendSDK abstract tests
# ===========================================================================


class TestMemoryBackendSDK:
    def test_concrete_backend_has_correct_tier(self):
        b = InMemoryBackend()
        assert b.tier == "in_memory"

    def test_concrete_backend_has_correct_priority(self):
        b = InMemoryBackend()
        assert b.priority == 10

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self):
        b = InMemoryBackend()
        record = MemoryRecord(content="Paris is the capital of France", memory_id="r1")
        await b.store(record)
        results = await b.retrieve("Paris", agent_id="agent-1", top_k=5)
        assert len(results) == 1
        assert results[0].memory_id == "r1"

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_for_no_match(self):
        b = InMemoryBackend()
        record = MemoryRecord(content="Python is a language", memory_id="r2")
        await b.store(record)
        results = await b.retrieve("Paris", agent_id="agent-1")
        assert results == []

    @pytest.mark.asyncio
    async def test_delete_removes_record(self):
        b = InMemoryBackend()
        record = MemoryRecord(content="test data", memory_id="r3")
        await b.store(record)
        await b.delete("r3")
        results = await b.retrieve("test", agent_id="agent-1")
        assert results == []

    @pytest.mark.asyncio
    async def test_delete_unknown_id_is_silent(self):
        b = InMemoryBackend()
        # Should not raise
        await b.delete("nonexistent-id")

    @pytest.mark.asyncio
    async def test_health_check_returns_true_by_default(self):
        b = InMemoryBackend()
        assert await b.health_check() is True

    def test_cannot_instantiate_abstract_backend_directly(self):
        with pytest.raises(TypeError):
            MemoryBackendSDK()  # type: ignore[abstract]


# ===========================================================================
# MemoryRegistry tests
# ===========================================================================


class TestMemoryRegistry:
    def test_register_and_get(self):
        b = InMemoryBackend()
        MemoryRegistry.register(b)
        assert MemoryRegistry.get("in_memory") is b

    def test_register_empty_tier_raises(self):
        class BadBackend(MemoryBackendSDK):
            tier = ""

            async def store(self, record): ...
            async def retrieve(self, query, *, agent_id, top_k=5): return []
            async def delete(self, memory_id): ...

        with pytest.raises(ValueError, match="tier attribute"):
            MemoryRegistry.register(BadBackend())

    def test_register_duplicate_tier_raises(self):
        MemoryRegistry.register(InMemoryBackend())
        with pytest.raises(ValueError, match="already registered"):
            MemoryRegistry.register(InMemoryBackend())

    def test_unregister_existing(self):
        b = InMemoryBackend()
        MemoryRegistry.register(b)
        MemoryRegistry.unregister("in_memory")
        assert MemoryRegistry.get("in_memory") is None

    def test_unregister_unknown_is_silent(self):
        MemoryRegistry.unregister("no_such_tier")  # should not raise

    def test_list_tiers(self):
        MemoryRegistry.register(InMemoryBackend())
        assert "in_memory" in MemoryRegistry.list_tiers()

    def test_list_backends_sorted_by_priority(self):
        class HighPriority(MemoryBackendSDK):
            tier = "high"
            priority = 1

            async def store(self, r): ...
            async def retrieve(self, q, *, agent_id, top_k=5): return []
            async def delete(self, mid): ...

        class LowPriority(MemoryBackendSDK):
            tier = "low"
            priority = 99

            async def store(self, r): ...
            async def retrieve(self, q, *, agent_id, top_k=5): return []
            async def delete(self, mid): ...

        MemoryRegistry.register(LowPriority())
        MemoryRegistry.register(HighPriority())
        backends = MemoryRegistry.list_backends()
        priorities = [b.priority for b in backends]
        assert priorities == sorted(priorities)

    def test_get_returns_none_for_unknown_tier(self):
        assert MemoryRegistry.get("ghost_tier") is None


# ===========================================================================
# EventSDK tests
# ===========================================================================


class TestEventSDKSubscribeUnsubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_registers_handler(self):
        received: list[BusEvent] = []

        async def handler(event: BusEvent) -> None:
            received.append(event)

        EventSDK.subscribe("test.event", handler)
        assert EventSDK.subscriber_count("test.event") == 1

    @pytest.mark.asyncio
    async def test_publish_dispatches_to_handler(self):
        received: list[BusEvent] = []

        async def handler(event: BusEvent) -> None:
            received.append(event)

        EventSDK.subscribe("test.dispatched", handler)
        await EventSDK.publish("test.dispatched", {"key": "val"}, publisher_id="test")
        assert len(received) == 1
        assert received[0].payload["key"] == "val"

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_handler(self):
        received: list[BusEvent] = []

        async def handler(event: BusEvent) -> None:
            received.append(event)

        EventSDK.subscribe("test.unsub", handler)
        EventSDK.unsubscribe("test.unsub", handler)
        await EventSDK.publish("test.unsub", {}, publisher_id="test")
        assert received == []

    def test_subscribe_sync_function_raises(self):
        def sync_fn(event):
            pass

        with pytest.raises(TypeError, match="async function"):
            EventSDK.subscribe("some.topic", sync_fn)  # type: ignore

    @pytest.mark.asyncio
    async def test_subscriber_count_returns_correct_number(self):
        async def h1(e): ...
        async def h2(e): ...

        EventSDK.subscribe("count.topic", h1)
        EventSDK.subscribe("count.topic", h2)
        assert EventSDK.subscriber_count("count.topic") == 2

    def test_get_bus_returns_bus_instance(self):
        from app.core.events.bus import AgentCommunicationBus

        assert isinstance(EventSDK.get_bus(), AgentCommunicationBus)


# ===========================================================================
# @on_event decorator tests
# ===========================================================================


class TestOnEventDecorator:
    @pytest.mark.asyncio
    async def test_decorator_subscribes_handler(self):
        received: list[BusEvent] = []

        @on_event("decorated.event")
        async def my_handler(event: BusEvent) -> None:
            received.append(event)

        await EventSDK.publish("decorated.event", {"x": 1}, publisher_id="test")
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_decorator_original_function_returned(self):
        """Decorated function should still be callable directly."""

        @on_event("direct.call.event")
        async def my_handler(event: BusEvent) -> None:
            pass

        # Should be directly callable without errors
        fake_event = BusEvent(
            event_id="id1",
            topic="direct.call.event",
            payload={},
            publisher_id="test",
        )
        await my_handler(fake_event)

    def test_decorator_sync_function_raises(self):
        with pytest.raises(TypeError, match="async function"):

            @on_event("sync.decorated")
            def not_async(event):
                pass

    @pytest.mark.asyncio
    async def test_decorator_exception_in_handler_is_suppressed(self):
        """Exceptions in the wrapped handler must not propagate to the bus."""
        call_count = 0

        @on_event("error.event")
        async def bad_handler(event: BusEvent) -> None:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("handler error")

        # publish should not raise even though handler raises
        await EventSDK.publish("error.event", {}, publisher_id="test")
        assert call_count == 1  # was called, exception was swallowed

    @pytest.mark.asyncio
    async def test_decorator_custom_error_handler_called(self):
        errors: list[tuple] = []

        async def my_error_handler(event: BusEvent, exc: Exception) -> None:
            errors.append((event.topic, str(exc)))

        @on_event("guarded.event", error_handler=my_error_handler)
        async def failing_handler(event: BusEvent) -> None:
            raise ValueError("intentional failure")

        await EventSDK.publish("guarded.event", {}, publisher_id="test")
        assert len(errors) == 1
        assert errors[0][0] == "guarded.event"
        assert "intentional failure" in errors[0][1]


# ===========================================================================
# TriggerSDK tests
# ===========================================================================


class TestTriggerSDK:
    def test_source_name_set(self):
        t = MockTrigger()
        assert t.source_name == "test.trigger"

    def test_publisher_id_defaults_to_source_name(self):
        t = MockTrigger()
        assert t.publisher_id == "test.trigger"

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        t = MockTrigger()
        await t.start()
        assert t.started is True
        await t.stop()
        assert t.stopped is True

    @pytest.mark.asyncio
    async def test_emit_publishes_prefixed_event(self):
        received: list[BusEvent] = []

        async def handler(event: BusEvent) -> None:
            received.append(event)

        EventSDK.subscribe("test.trigger.pr_opened", handler)
        t = MockTrigger()
        await t.emit("pr_opened", {"repo": "CortexFlow"})
        assert len(received) == 1
        assert received[0].topic == "test.trigger.pr_opened"
        assert received[0].payload["repo"] == "CortexFlow"

    @pytest.mark.asyncio
    async def test_emit_without_source_name_uses_raw_event_type(self):
        """If source_name is empty, emit uses event_type directly."""
        received: list[BusEvent] = []

        async def handler(event: BusEvent) -> None:
            received.append(event)

        class NoNameTrigger(TriggerSDK):
            source_name = ""

            async def start(self): ...
            async def stop(self): ...

        t = NoNameTrigger()
        EventSDK.subscribe("bare_event", handler)
        await t.emit("bare_event", {"data": 42})
        assert len(received) == 1
        assert received[0].payload["data"] == 42

    def test_cannot_instantiate_abstract_trigger(self):
        with pytest.raises(TypeError):
            TriggerSDK()  # type: ignore[abstract]


# ===========================================================================
# SDK __init__ re-exports
# ===========================================================================


class TestSDKExtensionsPublicApi:
    def test_memory_backend_sdk_importable(self):
        from app.sdk import MemoryBackendSDK as cls
        assert cls is MemoryBackendSDK

    def test_memory_record_importable(self):
        from app.sdk import MemoryRecord as cls
        assert cls is MemoryRecord

    def test_memory_registry_importable(self):
        from app.sdk import MemoryRegistry as cls
        assert cls is MemoryRegistry

    def test_event_sdk_importable(self):
        from app.sdk import EventSDK as cls
        assert cls is EventSDK

    def test_on_event_importable(self):
        from app.sdk import on_event as fn
        assert fn is on_event

    def test_trigger_sdk_importable(self):
        from app.sdk import TriggerSDK as cls
        assert cls is TriggerSDK

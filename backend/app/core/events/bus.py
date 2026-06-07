"""
AgentCommunicationBus — in-process async pub/sub event bus for inter-agent messaging.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

# Type alias for async subscriber handlers
Handler = Callable[["BusEvent"], Awaitable[None]]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BusEvent:
    """A single event published to the bus."""

    event_id: str
    topic: str
    payload: dict[str, Any]
    publisher_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "topic": self.topic,
            "payload": self.payload,
            "publisher_id": self.publisher_id,
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------


class AgentCommunicationBus:
    """
    In-process async publish/subscribe bus.

    Usage:
        bus = AgentCommunicationBus()

        async def on_event(event: BusEvent):
            ...

        bus.subscribe("my.topic", on_event)
        await bus.publish("my.topic", {"key": "value"}, publisher_id="agent-1")
    """

    def __init__(self) -> None:
        # topic -> list of handlers
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._event_history: list[BusEvent] = []

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Register *handler* to be called whenever an event on *topic* is dispatched."""
        if not callable(handler):
            raise TypeError("handler must be callable")
        if handler not in self._subscribers[topic]:
            self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        """Remove *handler* from *topic*. Silent if handler was not subscribed."""
        if handler in self._subscribers[topic]:
            self._subscribers[topic].remove(handler)

    def subscriber_count(self, topic: str) -> int:
        """Return how many handlers are subscribed to *topic*."""
        return len(self._subscribers[topic])

    @property
    def topics(self) -> list[str]:
        """Return all topics that have at least one subscriber."""
        return [t for t, handlers in self._subscribers.items() if handlers]

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        publisher_id: str,
    ) -> BusEvent:
        """
        Create a BusEvent, store it in history, dispatch to subscribers,
        and return the event.
        """
        if not topic:
            raise ValueError("topic must not be empty")
        event = BusEvent(
            event_id=uuid.uuid4().hex,
            topic=topic,
            payload=payload,
            publisher_id=publisher_id,
        )
        self._event_history.append(event)
        await self.dispatch(event)
        return event

    async def dispatch(self, event: BusEvent) -> int:
        """
        Dispatch *event* to all handlers subscribed to its topic.
        Returns the number of handlers called.
        """
        handlers = list(self._subscribers.get(event.topic, []))
        for handler in handlers:
            await handler(event)
        return len(handlers)

    # ------------------------------------------------------------------
    # History / introspection
    # ------------------------------------------------------------------

    @property
    def event_count(self) -> int:
        return len(self._event_history)

    def get_events(self, topic: str | None = None) -> list[BusEvent]:
        """Return all events, optionally filtered by topic."""
        if topic is None:
            return list(self._event_history)
        return [e for e in self._event_history if e.topic == topic]

    def clear_history(self) -> None:
        """Discard all stored events."""
        self._event_history.clear()

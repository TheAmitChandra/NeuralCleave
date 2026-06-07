"""
Event Handlers — route ``TriggerEvent`` objects from the event bus to the
appropriate downstream components (workflows, agents, notifications).

Architecture:
    TriggerEvent
        → EventRouter (selects matching handlers by topic pattern)
            → WorkflowEventHandler   (creates/resumes workflow executions)
            → AgentEventHandler      (broadcasts event to subscribed agents)
            → NotificationEventHandler (logs / notifies operators)
"""

from __future__ import annotations

import fnmatch
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from app.core.events.triggers import TriggerEvent, TriggerStatus

# ---------------------------------------------------------------------------
# Protocols / base
# ---------------------------------------------------------------------------


class EventHandler(Protocol):
    """Protocol for all event handler implementations."""

    async def handle(self, event: TriggerEvent) -> "HandlerResult":
        """Process *event* and return a result."""
        ...


# ---------------------------------------------------------------------------
# Result data class
# ---------------------------------------------------------------------------


@dataclass
class HandlerResult:
    """Outcome of a single handler invocation."""

    handler_name: str
    event_id: str
    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    processed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "handler_name": self.handler_name,
            "event_id": self.event_id,
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "processed_at": self.processed_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# WorkflowEventHandler
# ---------------------------------------------------------------------------


class WorkflowEventHandler:
    """
    Translates incoming events into workflow execution requests.

    In production this creates a Celery task or writes a pending workflow row;
    in the current implementation it records the dispatch for auditability.
    """

    def __init__(self) -> None:
        self.name = "WorkflowEventHandler"
        self._dispatch_log: list[dict[str, Any]] = []

    async def handle(self, event: TriggerEvent) -> HandlerResult:
        """Create a workflow execution record for *event*."""
        execution_id = str(uuid.uuid4())
        record = {
            "execution_id": execution_id,
            "trigger_id": event.trigger_id,
            "topic": event.topic,
            "source": event.source,
            "payload": event.payload,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
        }
        self._dispatch_log.append(record)
        event.status = TriggerStatus.PROCESSING

        return HandlerResult(
            handler_name=self.name,
            event_id=event.trigger_id,
            success=True,
            message=f"Workflow execution {execution_id} queued",
            data={"execution_id": execution_id},
        )

    def dispatched(self) -> list[dict[str, Any]]:
        """Return all dispatched workflow records (for testing / audit)."""
        return list(self._dispatch_log)

    def clear(self) -> None:
        self._dispatch_log.clear()


# ---------------------------------------------------------------------------
# AgentEventHandler
# ---------------------------------------------------------------------------


class AgentEventHandler:
    """
    Broadcasts a ``TriggerEvent`` to all agents subscribed to its topic.

    Agent subscriptions are stored as a mapping of
    ``{topic_pattern: [agent_id, …]}``.  Glob-style patterns are supported
    (e.g. ``"github.*"`` matches ``"github.push"``).
    """

    def __init__(self) -> None:
        self.name = "AgentEventHandler"
        # pattern → list of agent_ids
        self._subscriptions: dict[str, list[str]] = {}
        self._notifications: list[dict[str, Any]] = []

    # --- Subscription management -------------------------------------------

    def subscribe(self, agent_id: str, topic_pattern: str) -> None:
        """Subscribe *agent_id* to events matching *topic_pattern*."""
        self._subscriptions.setdefault(topic_pattern, [])
        if agent_id not in self._subscriptions[topic_pattern]:
            self._subscriptions[topic_pattern].append(agent_id)

    def unsubscribe(self, agent_id: str, topic_pattern: str) -> bool:
        """Remove *agent_id* from *topic_pattern*. Returns True if removed."""
        agents = self._subscriptions.get(topic_pattern, [])
        if agent_id in agents:
            agents.remove(agent_id)
            return True
        return False

    def subscribed_agents(self, topic: str) -> list[str]:
        """Return all agent IDs whose subscription patterns match *topic*."""
        matched: list[str] = []
        for pattern, agents in self._subscriptions.items():
            if fnmatch.fnmatch(topic, pattern):
                for a in agents:
                    if a not in matched:
                        matched.append(a)
        return matched

    # --- Handler -----------------------------------------------------------

    async def handle(self, event: TriggerEvent) -> HandlerResult:
        """Notify all subscribed agents about *event*."""
        agents = self.subscribed_agents(event.topic)
        for agent_id in agents:
            self._notifications.append(
                {
                    "agent_id": agent_id,
                    "event_id": event.trigger_id,
                    "topic": event.topic,
                    "notified_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        return HandlerResult(
            handler_name=self.name,
            event_id=event.trigger_id,
            success=True,
            message=f"Notified {len(agents)} agent(s)",
            data={"agent_ids": agents, "count": len(agents)},
        )

    def notifications(self) -> list[dict[str, Any]]:
        return list(self._notifications)

    def clear(self) -> None:
        self._notifications.clear()


# ---------------------------------------------------------------------------
# NotificationEventHandler
# ---------------------------------------------------------------------------


class NotificationEventHandler:
    """
    Records events to an in-memory audit log and (optionally) forwards
    high-severity events to a configured webhook URL.

    In production, forwarding would use an async HTTP client; here the
    destination is captured in ``_forwarded`` for testability.
    """

    FORWARD_TOPICS = frozenset(
        {
            "monitoring.alert.critical",
            "monitoring.alert.warning",
            "security.threat.detected",
        }
    )

    def __init__(self, webhook_url: str | None = None) -> None:
        self.name = "NotificationEventHandler"
        self._webhook_url = webhook_url
        self._audit: list[dict[str, Any]] = []
        self._forwarded: list[dict[str, Any]] = []

    async def handle(self, event: TriggerEvent) -> HandlerResult:
        entry = {
            "event_id": event.trigger_id,
            "topic": event.topic,
            "source": event.source,
            "trigger_type": event.trigger_type.value,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
        self._audit.append(entry)

        forwarded = False
        if event.topic in self.FORWARD_TOPICS and self._webhook_url:
            self._forwarded.append(
                {
                    "url": self._webhook_url,
                    "event_id": event.trigger_id,
                    "topic": event.topic,
                }
            )
            forwarded = True

        return HandlerResult(
            handler_name=self.name,
            event_id=event.trigger_id,
            success=True,
            message="Event logged" + (" and forwarded" if forwarded else ""),
            data={"forwarded": forwarded},
        )

    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit)

    def forwarded(self) -> list[dict[str, Any]]:
        return list(self._forwarded)

    def clear(self) -> None:
        self._audit.clear()
        self._forwarded.clear()


# ---------------------------------------------------------------------------
# EventRouter
# ---------------------------------------------------------------------------


@dataclass
class _Registration:
    """Internal handler registration entry."""

    topic_pattern: str
    handler: Any  # EventHandler implementor
    priority: int = 0  # higher = executed first


class EventRouter:
    """
    Routes a ``TriggerEvent`` to all handlers whose topic pattern matches
    the event's topic.

    Multiple handlers may match; they are called in descending priority order.
    All results are collected and returned.

    Usage::

        router = EventRouter()
        router.register("github.*", GitHubWorkflowHandler(), priority=10)
        router.register("*", NotificationEventHandler(), priority=0)

        results = await router.dispatch(event)
    """

    def __init__(self) -> None:
        self._registrations: list[_Registration] = []

    def register(
        self,
        topic_pattern: str,
        handler: Any,
        priority: int = 0,
    ) -> None:
        """Register *handler* for events matching *topic_pattern* (glob syntax)."""
        self._registrations.append(
            _Registration(topic_pattern=topic_pattern, handler=handler, priority=priority)
        )
        # Keep sorted: higher priority first
        self._registrations.sort(key=lambda r: r.priority, reverse=True)

    def matching_handlers(self, topic: str) -> list[Any]:
        """Return handlers (in priority order) whose patterns match *topic*."""
        return [r.handler for r in self._registrations if fnmatch.fnmatch(topic, r.topic_pattern)]

    async def dispatch(self, event: TriggerEvent) -> list[HandlerResult]:
        """
        Dispatch *event* to all matching handlers.

        Returns a list of ``HandlerResult`` objects, one per handler.
        Failed handlers do not prevent subsequent handlers from running.
        """
        handlers = self.matching_handlers(event.topic)
        results: list[HandlerResult] = []
        for handler in handlers:
            try:
                result = await handler.handle(event)
                results.append(result)
            except Exception as exc:  # noqa: BLE001
                results.append(
                    HandlerResult(
                        handler_name=getattr(handler, "name", type(handler).__name__),
                        event_id=event.trigger_id,
                        success=False,
                        message=f"Handler raised {type(exc).__name__}: {exc}",
                    )
                )
        return results

    def registered_count(self) -> int:
        return len(self._registrations)

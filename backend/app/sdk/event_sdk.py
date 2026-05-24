"""CortexFlow Event SDK — API for plugin event subscriptions and custom triggers.

Plugin authors can:
1. Subscribe handlers to CortexFlow system events (tool calls, agent transitions,
   workflow completions, security alerts, etc.)
2. Publish custom events into the event bus for other plugins or agents to consume
3. Declare custom trigger sources via :class:`TriggerSDK`

Architecture
────────────
                  ┌─────────────────────────────────────┐
    Plugin file   │ @on_event("agent.state_changed")    │
                  │ async def my_handler(event): ...    │
                  └──────────────┬──────────────────────┘
                                 │ EventSDK.subscribe(...)
                  ┌──────────────▼──────────────────────┐
                  │     AgentCommunicationBus            │  ← existing CortexFlow bus
                  │  (Redis pub/sub + in-process async)  │
                  └─────────────────────────────────────-┘

Built-in system event topics (subscribable by plugins):
    agent.created               — new agent registered
    agent.state_changed         — IDLE→PLANNING, PLANNING→EXECUTING, etc.
    agent.terminated            — agent shut down
    tool.call.started           — tool execution began (payload: tool_name, agent_id)
    tool.call.completed         — tool result available (payload: + output, success)
    tool.call.failed            — tool raised exception (payload: + error)
    workflow.started            — workflow execution began
    workflow.completed          — workflow finished successfully
    workflow.failed             — workflow failed or rolled back
    memory.stored               — a memory entry was persisted
    memory.retrieved            — retrieval pipeline returned results
    security.threat_detected    — prompt injection / risk threshold breach
    security.approval_requested — human approval gate opened
    security.approval_resolved  — approval accepted or rejected

Usage — decorator style::

    from app.sdk import on_event, EventSDK

    @on_event("tool.call.completed")
    async def track_completions(event):
        print(f"Tool {event.payload['tool_name']} finished in {event.payload.get('ms')}ms")

Usage — class-based trigger source::

    from app.sdk import TriggerSDK

    class GitHubPRTrigger(TriggerSDK):
        source_name = "github.pr"

        async def start(self) -> None:
            # Start a webhook listener or polling loop
            ...

        async def stop(self) -> None:
            # Clean up
            ...
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable

from app.core.events.bus import AgentCommunicationBus, BusEvent
from app.core.observability.logs import get_logger

logger = get_logger(__name__)

# Type alias for event handler coroutines
EventHandler = Callable[[BusEvent], Awaitable[None]]


# ---------------------------------------------------------------------------
# EventSDK — pub/sub interface for plugin event handlers
# ---------------------------------------------------------------------------


class EventSDK:
    """Facade over :class:`AgentCommunicationBus` for plugin authors.

    Plugin code should use this class rather than accessing
    ``AgentCommunicationBus`` directly — it adds logging, error isolation,
    and a stable API surface.

    All methods are class-level (no instantiation required) and delegate to
    a shared bus instance.

    Usage::

        EventSDK.subscribe("agent.state_changed", my_async_handler)
        await EventSDK.publish("my.plugin.event", {"key": "value"}, publisher_id="my_plugin")
        EventSDK.unsubscribe("agent.state_changed", my_async_handler)
    """

    # Shared bus — plugins share the same in-process bus as the core system
    _bus: AgentCommunicationBus = AgentCommunicationBus()

    @classmethod
    def subscribe(cls, topic: str, handler: EventHandler) -> None:
        """Register *handler* to be called for every event on *topic*.

        Parameters
        ----------
        topic:
            The event topic string. Supports exact matches and wildcard suffix
            patterns, e.g. ``"tool.call.*"`` matches all tool call events.
        handler:
            An ``async def`` coroutine accepting a single :class:`BusEvent` arg.
        """
        if not asyncio.iscoroutinefunction(handler):
            raise TypeError(
                f"EventSDK.subscribe: handler '{getattr(handler, '__name__', handler)}' "
                "must be an async function (defined with 'async def')"
            )
        cls._bus.subscribe(topic, handler)
        logger.info(
            "sdk.event_subscribed",
            topic=topic,
            handler=getattr(handler, "__name__", repr(handler)),
        )

    @classmethod
    def unsubscribe(cls, topic: str, handler: EventHandler) -> None:
        """Remove *handler* from *topic*. Silent if not subscribed."""
        cls._bus.unsubscribe(topic, handler)
        logger.info(
            "sdk.event_unsubscribed",
            topic=topic,
            handler=getattr(handler, "__name__", repr(handler)),
        )

    @classmethod
    async def publish(
        cls,
        topic: str,
        payload: dict[str, Any],
        *,
        publisher_id: str = "sdk_plugin",
    ) -> None:
        """Publish a custom event to the bus.

        Parameters
        ----------
        topic:
            The event topic. Use a plugin-scoped prefix to avoid collisions,
            e.g. ``"my_plugin.event_name"``.
        payload:
            Arbitrary JSON-serialisable data.
        publisher_id:
            Identifier for the publishing plugin (for audit logging).
        """
        await cls._bus.publish(topic, payload, publisher_id=publisher_id)
        logger.debug("sdk.event_published", topic=topic, publisher_id=publisher_id)

    @classmethod
    def subscriber_count(cls, topic: str) -> int:
        """Return the number of handlers currently subscribed to *topic*."""
        return cls._bus.subscriber_count(topic)

    @classmethod
    def get_bus(cls) -> AgentCommunicationBus:
        """Return the underlying bus instance for advanced use cases."""
        return cls._bus


# ---------------------------------------------------------------------------
# @on_event — decorator shorthand
# ---------------------------------------------------------------------------


def on_event(
    topic: str,
    *,
    error_handler: EventHandler | None = None,
) -> Callable:
    """Decorator that subscribes an async function to *topic*.

    The decorated function is returned unchanged and also registered as a
    handler on the shared event bus.

    Parameters
    ----------
    topic:
        The event topic to subscribe to.
    error_handler:
        Optional async callable invoked when the decorated handler raises.
        Receives ``(event, exception)`` as positional arguments.
        If None, exceptions are logged and suppressed (bus is not disrupted).

    Example::

        @on_event("workflow.completed")
        async def on_workflow_done(event: BusEvent) -> None:
            print(f"Workflow {event.payload['workflow_id']} completed!")
    """

    def decorator(fn: Callable) -> Callable:
        if not asyncio.iscoroutinefunction(fn):
            raise TypeError(
                f"@on_event: '{fn.__name__}' must be an async function "
                "(defined with 'async def')"
            )

        async def _safe_handler(event: BusEvent) -> None:
            try:
                await fn(event)
            except Exception as exc:
                if error_handler is not None:
                    try:
                        await error_handler(event, exc)  # type: ignore[call-arg]
                    except Exception:
                        logger.exception(
                            "sdk.event_handler_error_handler_failed",
                            topic=topic,
                            handler=fn.__name__,
                        )
                else:
                    logger.exception(
                        "sdk.event_handler_exception",
                        topic=topic,
                        handler=fn.__name__,
                        error=str(exc),
                    )

        _safe_handler.__name__ = fn.__name__
        _safe_handler.__wrapped__ = fn  # type: ignore[attr-defined]

        EventSDK.subscribe(topic, _safe_handler)
        return fn  # return original — can still be called directly in tests

    return decorator


# ---------------------------------------------------------------------------
# TriggerSDK — base class for custom event trigger sources
# ---------------------------------------------------------------------------


class TriggerSDK(ABC):
    """Base class for custom event trigger sources.

    A trigger source listens for external events (webhooks, polling, file
    watchers, IMAP, etc.) and publishes them into CortexFlow's event bus.

    Class attributes
    ────────────────
    source_name      Unique name for this trigger source (e.g. ``"github.pr"``).
                     Events published by this source should be prefixed with it.
    publisher_id     Identifies this source in audit logs.
    """

    source_name: str = ""
    publisher_id: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.publisher_id:
            cls.publisher_id = cls.source_name or cls.__name__

    @abstractmethod
    async def start(self) -> None:
        """Begin listening for external events.

        Called once during CortexFlow startup (or when the trigger is activated).
        Typically starts a background task or opens a network connection.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop the trigger and release all resources.

        Called during CortexFlow shutdown. Must not raise.
        """

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Convenience method — publish an event prefixed with :attr:`source_name`.

        Parameters
        ----------
        event_type:
            Short event type (e.g. ``"pr_opened"``). Will be published as
            ``"{source_name}.{event_type}"`` on the bus.
        payload:
            Arbitrary JSON-serialisable event data.
        """
        topic = f"{self.source_name}.{event_type}" if self.source_name else event_type
        await EventSDK.publish(topic, payload, publisher_id=self.publisher_id)

"""Agent heartbeat system — periodic health evaluation and goal monitoring.

``HeartbeatMonitor`` fires registered async callbacks on a configurable
interval.  Callback failures are logged and recorded in the ``HeartbeatResult``
but do NOT stop the monitor — callers decide how to handle unhealthy agents.

Typical usage
-------------
    monitor = HeartbeatMonitor("agent-001", interval_seconds=10.0)

    async def check_goals(hb: HeartbeatMonitor) -> None:
        if not goals_met():
            raise RuntimeError("Goals not progressing")

    monitor.add_callback(check_goals)
    await monitor.start()
    # ... later ...
    await monitor.stop()
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from app.core.observability.logs import get_logger

logger = get_logger(__name__)

# Type alias for heartbeat callbacks
HeartbeatCallback = Callable[["HeartbeatMonitor"], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# HeartbeatResult
# ---------------------------------------------------------------------------


@dataclass
class HeartbeatResult:
    """Outcome of a single heartbeat evaluation."""

    agent_id: str
    beat_number: int
    timestamp: float = field(default_factory=time.time)
    healthy: bool = True
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "beat_number": self.beat_number,
            "timestamp": self.timestamp,
            "healthy": self.healthy,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# HeartbeatMonitor
# ---------------------------------------------------------------------------


class HeartbeatMonitor:
    """Periodically fires callbacks to evaluate agent health and goals.

    Parameters
    ----------
    agent_id:
        Identifier of the agent being monitored.
    interval_seconds:
        Time between automatic heartbeat firings.  Defaults to 30 s.
    callbacks:
        Optional initial list of async callback coroutines.
    """

    def __init__(
        self,
        agent_id: str,
        interval_seconds: float = 30.0,
        *,
        callbacks: list[HeartbeatCallback] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.interval_seconds = interval_seconds
        self._callbacks: list[HeartbeatCallback] = list(callbacks or [])
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._beat_count = 0
        self.last_beat: HeartbeatResult | None = None

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def add_callback(self, cb: HeartbeatCallback) -> None:
        """Register a new heartbeat callback."""
        self._callbacks.append(cb)

    def remove_callback(self, cb: HeartbeatCallback) -> None:
        """Deregister a previously registered callback (no-op if absent)."""
        with suppress(ValueError):
            self._callbacks.remove(cb)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the periodic heartbeat loop (idempotent)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name=f"heartbeat-{self.agent_id}")
        logger.info(
            "heartbeat.started",
            agent_id=self.agent_id,
            interval_seconds=self.interval_seconds,
        )

    async def stop(self) -> None:
        """Stop the periodic loop and wait for it to finish (idempotent)."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        logger.info(
            "heartbeat.stopped",
            agent_id=self.agent_id,
            total_beats=self._beat_count,
        )

    # ------------------------------------------------------------------
    # Manual / internal beat
    # ------------------------------------------------------------------

    async def beat(self) -> HeartbeatResult:
        """Fire all callbacks once and return the aggregated result.

        This method is called automatically by the internal loop but can
        also be triggered manually (e.g., in tests or on-demand checks).
        """
        self._beat_count += 1
        result = HeartbeatResult(agent_id=self.agent_id, beat_number=self._beat_count)
        for cb in self._callbacks:
            try:
                await cb(self)
            except Exception as exc:
                result.healthy = False
                result.details.setdefault("errors", []).append(str(exc))
                logger.warning(
                    "heartbeat.callback_failed",
                    agent_id=self.agent_id,
                    beat=self._beat_count,
                    error=str(exc),
                )
        self.last_beat = result
        logger.debug(
            "heartbeat.beat",
            agent_id=self.agent_id,
            beat=self._beat_count,
            healthy=result.healthy,
        )
        return result

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def beat_count(self) -> int:
        """Total number of heartbeat beats fired (including manual ones)."""
        return self._beat_count

    @property
    def is_running(self) -> bool:
        """True while the periodic loop is active."""
        return self._running

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.interval_seconds)
            if self._running:
                await self.beat()

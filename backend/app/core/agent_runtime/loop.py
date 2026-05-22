"""Autonomous execution loop — outer driver for AgentRuntime.

``ExecutionLoop`` wraps an ``AgentRuntime`` to provide:
  - ``max_iterations`` cap (useful in tests and bounded batch runs)
  - Aggregated loop statistics (iterations, tasks, uptime)
  - Graceful ``stop()`` signal via asyncio.Event
  - Per-iteration idle polling with configurable interval

Typical usage
-------------
    config = AgentConfig(name="worker-1")
    runtime = AgentRuntime("agent-001", config)
    loop = ExecutionLoop(runtime, LoopConfig(max_iterations=100))
    stats = await loop.run()
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.agent_runtime.agent import AgentRuntime, AgentState, AgentConfig, AgentTask
from app.core.observability.logs import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# LoopConfig
# ---------------------------------------------------------------------------

@dataclass
class LoopConfig:
    """Configuration for ExecutionLoop."""

    max_iterations: int = 0
    """Maximum iterations before the loop exits automatically.
    ``0`` means run indefinitely (until ``stop()`` is called)."""

    idle_poll_interval: float = 0.05
    """Seconds between queue-poll iterations when the agent is idle."""

    task_timeout_seconds: float = 300.0
    """Per-task hard timeout passed to the runtime (informational)."""

    enable_metrics: bool = True
    """Whether to emit per-iteration metrics to the observability stack."""


# ---------------------------------------------------------------------------
# LoopStats
# ---------------------------------------------------------------------------

@dataclass
class LoopStats:
    """Accumulated statistics from a single loop run."""

    iterations: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_task_duration_seconds: float = 0.0
    start_time: float = field(default_factory=time.time)

    @property
    def uptime_seconds(self) -> float:
        """Wall-clock seconds since the loop started."""
        return time.time() - self.start_time

    def to_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "total_task_duration_seconds": round(self.total_task_duration_seconds, 3),
            "uptime_seconds": round(self.uptime_seconds, 3),
        }


# ---------------------------------------------------------------------------
# ExecutionLoop
# ---------------------------------------------------------------------------

class ExecutionLoop:
    """Drives an AgentRuntime through repeated cognitive pipeline iterations.

    Parameters
    ----------
    runtime:
        The AgentRuntime instance to drive.
    config:
        Loop behaviour configuration.  Defaults to ``LoopConfig()``.
    """

    def __init__(
        self,
        runtime: AgentRuntime,
        config: LoopConfig | None = None,
    ) -> None:
        self.runtime = runtime
        self.config = config or LoopConfig()
        self.stats = LoopStats()
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> LoopStats:
        """Start the runtime and run the execution loop.

        The loop exits when:
        - ``stop()`` is called, OR
        - ``config.max_iterations`` is reached (if > 0), OR
        - the runtime transitions to TERMINATED

        Returns
        -------
        LoopStats
            Accumulated statistics for the completed run.
        """
        if self.runtime.state == AgentState.TERMINATED:
            logger.info(
                "execution_loop.runtime_already_terminated",
                agent_id=self.runtime.agent_id,
            )
            return self.stats
        await self.runtime.start()
        logger.info(
            "execution_loop.started",
            agent_id=self.runtime.agent_id,
            max_iterations=self.config.max_iterations,
            idle_poll_interval=self.config.idle_poll_interval,
        )
        try:
            await self._loop()
        finally:
            if self.runtime.state != AgentState.TERMINATED:
                await self.runtime.stop()
            logger.info(
                "execution_loop.finished",
                agent_id=self.runtime.agent_id,
                **self.stats.to_dict(),
            )
        return self.stats

    async def stop(self) -> None:
        """Signal the loop to stop after the current iteration completes."""
        self._stop_event.set()
        logger.debug("execution_loop.stop_requested", agent_id=self.runtime.agent_id)

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            max_iter = self.config.max_iterations
            if max_iter > 0 and self.stats.iterations >= max_iter:
                logger.info(
                    "execution_loop.max_iterations_reached",
                    agent_id=self.runtime.agent_id,
                    iterations=self.stats.iterations,
                )
                break
            if self.runtime.state == AgentState.TERMINATED:
                break

            self.stats.iterations += 1
            await asyncio.sleep(self.config.idle_poll_interval)

    # ------------------------------------------------------------------
    # Factory helper
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, agent_id: str, agent_config: AgentConfig, loop_config: LoopConfig | None = None) -> "ExecutionLoop":
        """Convenience factory: build a runtime + loop from configs."""
        runtime = AgentRuntime(agent_id, agent_config)
        return cls(runtime, loop_config)

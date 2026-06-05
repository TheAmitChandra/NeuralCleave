"""Agent Runtime — AgentRuntime class, AgentState enum, AgentConfig, AgentTask.

The AgentRuntime drives a single autonomous agent through the CortexFlow
cognitive pipeline:
    IDLE → PLANNING → EXECUTING → VALIDATING → REFLECTING → IDLE (loop)

State management is asyncio-native; all public methods are coroutines.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.core.observability.logs import get_logger
from app.core.observability.metrics import get_metrics
from app.core.observability.tracing import traced_operation

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# AgentState
# ---------------------------------------------------------------------------

class AgentState(str, Enum):
    """All possible states for an AgentRuntime instance."""

    IDLE = "IDLE"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VALIDATING = "VALIDATING"
    REFLECTING = "REFLECTING"
    PAUSED = "PAUSED"
    TERMINATED = "TERMINATED"


# ---------------------------------------------------------------------------
# AgentConfig
# ---------------------------------------------------------------------------

class AgentConfig(BaseModel):
    """Pydantic configuration model for AgentRuntime."""

    name: str
    agent_type: str = "generic"
    max_concurrent_tasks: int = 1
    heartbeat_interval_seconds: float = 30.0
    task_timeout_seconds: float = 300.0
    max_retries: int = 3
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# AgentTask
# ---------------------------------------------------------------------------

@dataclass
class AgentTask:
    """A unit of work submitted to an AgentRuntime."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# AgentRuntime
# ---------------------------------------------------------------------------

class AgentRuntime:
    """Core autonomous agent runtime.

    Responsibilities
    ----------------
    - Agent lifecycle management (idle → planning → executing → validating →
      reflecting → idle, or pause/resume/terminate at any point)
    - Async task queue processing
    - Per-task cognitive pipeline (plan → execute → validate → reflect)
    - Integration with observability (metrics, tracing, structured logs)

    Thread safety
    -------------
    State transitions are serialised via ``_state_lock`` (asyncio.Lock).
    All public methods must be awaited from an asyncio event loop.
    """

    def __init__(self, agent_id: str, config: AgentConfig) -> None:
        self.agent_id = agent_id
        self.config = config

        self._state: AgentState = AgentState.IDLE
        self._state_lock = asyncio.Lock()

        self._task_queue: asyncio.Queue[AgentTask] = asyncio.Queue()
        self._current_task: AgentTask | None = None

        self._loop_task: asyncio.Task[None] | None = None
        self._terminated = asyncio.Event()
        self._paused = asyncio.Event()
        self._paused.set()  # not paused on construction

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> AgentState:
        """Current agent state (non-blocking read)."""
        return self._state

    @property
    def current_task(self) -> AgentTask | None:
        """The task currently being processed, or None."""
        return self._current_task

    @property
    def queue_size(self) -> int:
        """Number of tasks waiting in the queue."""
        return self._task_queue.qsize()

    # ------------------------------------------------------------------
    # Lifecycle control
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background execution loop.

        Raises
        ------
        RuntimeError
            If the agent has already been terminated.
        """
        if self._state == AgentState.TERMINATED:
            raise RuntimeError(
                f"Agent {self.agent_id!r} is TERMINATED and cannot be restarted."
            )
        await self._set_state(AgentState.IDLE)
        self._loop_task = asyncio.create_task(self._run_loop(), name=f"agent-{self.agent_id}")
        logger.info("agent.started", agent_id=self.agent_id, name=self.config.name)

    async def stop(self) -> None:
        """Gracefully terminate the agent.

        Cancels the background loop and waits for it to finish.
        Safe to call multiple times.
        """
        await self._set_state(AgentState.TERMINATED)
        self._terminated.set()
        self._paused.set()  # unblock if currently paused
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task
        logger.info("agent.stopped", agent_id=self.agent_id)

    async def pause(self) -> None:
        """Pause execution; the current task will complete before pausing.

        Raises
        ------
        RuntimeError
            If the agent is already terminated.
        """
        if self._state == AgentState.TERMINATED:
            raise RuntimeError(
                f"Cannot pause terminated agent {self.agent_id!r}."
            )
        self._paused.clear()
        await self._set_state(AgentState.PAUSED)
        logger.info("agent.paused", agent_id=self.agent_id)

    async def resume(self) -> None:
        """Resume from PAUSED state.

        Raises
        ------
        RuntimeError
            If the agent is not currently paused.
        """
        if self._state != AgentState.PAUSED:
            raise RuntimeError(
                f"Agent {self.agent_id!r} is not PAUSED (current={self._state.value})."
            )
        self._paused.set()
        await self._set_state(AgentState.IDLE)
        logger.info("agent.resumed", agent_id=self.agent_id)

    # ------------------------------------------------------------------
    # Task submission
    # ------------------------------------------------------------------

    async def submit_task(self, task: AgentTask) -> None:
        """Enqueue a task for execution.

        Raises
        ------
        RuntimeError
            If the agent is terminated.
        """
        if self._state == AgentState.TERMINATED:
            raise RuntimeError(
                f"Cannot submit tasks to terminated agent {self.agent_id!r}."
            )
        await self._task_queue.put(task)
        logger.debug(
            "agent.task_submitted",
            agent_id=self.agent_id,
            task_id=task.task_id,
            queue_size=self._task_queue.qsize(),
        )

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Background task: dequeue and execute tasks until terminated."""
        while not self._terminated.is_set():
            # Block while paused; unblocked by resume() or stop()
            await self._paused.wait()
            if self._terminated.is_set():
                break
            try:
                task = await asyncio.wait_for(self._task_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            await self._execute_task(task)

    async def _execute_task(self, task: AgentTask) -> None:
        """Run a single task through the full cognitive pipeline."""
        self._current_task = task
        async with traced_operation(
            f"agent.task",
            attributes={
                "agent_id": self.agent_id,
                "task_id": task.task_id,
                "agent_type": self.config.agent_type,
            },
        ):
            try:
                await self._set_state(AgentState.PLANNING)
                await self._plan(task)

                await self._set_state(AgentState.EXECUTING)
                await self._execute(task)

                await self._set_state(AgentState.VALIDATING)
                await self._validate(task)

                await self._set_state(AgentState.REFLECTING)
                await self._reflect(task)

                try:
                    m = get_metrics()
                    m.agent_tasks_total.labels(
                        agent_type=self.config.agent_type, status="completed"
                    ).inc()
                except Exception:  # pragma: no cover
                    pass

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "agent.task_failed",
                    agent_id=self.agent_id,
                    task_id=task.task_id,
                    error=str(exc),
                )
                try:
                    m = get_metrics()
                    m.agent_tasks_total.labels(
                        agent_type=self.config.agent_type, status="failed"
                    ).inc()
                except Exception:  # pragma: no cover
                    pass
            finally:
                self._current_task = None
                if self._state not in {AgentState.TERMINATED, AgentState.PAUSED}:
                    await self._set_state(AgentState.IDLE)

    # ------------------------------------------------------------------
    # Cognitive pipeline hooks (override in subclasses)
    # ------------------------------------------------------------------

    async def _plan(self, task: AgentTask) -> None:
        """Planning phase: decompose task into executable steps."""
        logger.debug("agent.planning", agent_id=self.agent_id, task_id=task.task_id)
        try:
            from app.core.model_router.router import model_router

            prompt = (
                f"You are a cognitive agent planning assistant.\n"
                f"Task Description: {task.description}\n"
                f"Task Payload: {task.payload}\n\n"
                f"Decompose the task above into a list of clear execution steps."
            )
            response = await model_router.generate(
                prompt=prompt,
                task_type="task_decomposition",
                agent_id=self.agent_id,
                task_id=task.task_id,
            )
            task.payload["plan"] = response
            logger.info("agent.planning.success", agent_id=self.agent_id, task_id=task.task_id)
        except Exception as exc:
            logger.error("agent.planning.failed", agent_id=self.agent_id, task_id=task.task_id, error=str(exc))
            task.payload["plan"] = f"Execute: {task.description}"

    async def _execute(self, task: AgentTask) -> None:  # noqa: B027
        """Execution phase: invoke tools and collect results."""
        logger.debug("agent.executing", agent_id=self.agent_id, task_id=task.task_id)

    async def _validate(self, task: AgentTask) -> None:  # noqa: B027
        """Validation phase: verify result correctness."""
        logger.debug("agent.validating", agent_id=self.agent_id, task_id=task.task_id)

    async def _reflect(self, task: AgentTask) -> None:  # noqa: B027
        """Reflection phase: score quality and store insights."""
        logger.debug("agent.reflecting", agent_id=self.agent_id, task_id=task.task_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _set_state(self, new_state: AgentState) -> None:
        async with self._state_lock:
            old = self._state
            self._state = new_state
            logger.debug(
                "agent.state_change",
                agent_id=self.agent_id,
                from_state=old.value,
                to_state=new_state.value,
            )
            # Update Prometheus gauge: 1 when active, 0 when not
            active = new_state not in {AgentState.TERMINATED, AgentState.PAUSED, AgentState.IDLE}
            try:
                m = get_metrics()
                m.agents_active.labels(agent_type=self.config.agent_type).set(
                    1 if active else 0
                )
            except Exception:  # pragma: no cover
                pass

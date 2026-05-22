"""
executor.py — ExecutorAgent

Executes SubTasks individually or in batches, delegating to
registered handlers or tool registries when available.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.core.orchestration.planner import SubTask


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ExecutionResult:
    """The outcome of executing a single SubTask."""

    task_id: str
    success: bool
    output: Any = None
    duration_seconds: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output": self.output,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


# Type alias for task handlers
TaskHandler = Callable[[SubTask, Any], Awaitable[Any]]


# ---------------------------------------------------------------------------
# ExecutorAgent
# ---------------------------------------------------------------------------


class ExecutorAgent:
    """Executes SubTasks, dispatching to registered handlers or tool registries.

    Handler lookup order:
    1. ``task.payload["task_type"]`` → registered handler
    2. ``tool_registry`` + ``task.payload["tool"]`` → tool registry lookup
    3. No-op: returns ``{"executed": task.description}`` (base / testing)
    """

    def __init__(
        self,
        agent_id: str | None = None,
        default_timeout: float = 30.0,
    ) -> None:
        self.agent_id: str = agent_id or str(uuid.uuid4())
        self.default_timeout: float = default_timeout
        self._handlers: dict[str, TaskHandler] = {}

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def register_handler(self, task_type: str, handler: TaskHandler) -> None:
        """Register an async handler for a given task type."""
        self._handlers[task_type] = handler

    def get_handler(self, task_type: str) -> TaskHandler | None:
        return self._handlers.get(task_type)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        task: SubTask,
        tool_registry: Any = None,
        timeout: float | None = None,
    ) -> ExecutionResult:
        """Execute a single SubTask and return an ExecutionResult."""
        t0 = time.monotonic()
        effective_timeout = timeout if timeout is not None else self.default_timeout

        try:
            task_type = task.payload.get("task_type", "")
            handler = self._handlers.get(task_type)

            if handler:
                output = await asyncio.wait_for(
                    handler(task, tool_registry), timeout=effective_timeout
                )
            elif tool_registry is not None:
                tool_name = task.payload.get("tool")
                if tool_name:
                    tool = tool_registry.get_tool(tool_name)
                    output = await asyncio.wait_for(
                        tool.execute(**task.payload.get("args", {})),
                        timeout=effective_timeout,
                    )
                else:
                    output = {"executed": task.description}
            else:
                # Base / testing: no-op execution
                output = {"executed": task.description}

            return ExecutionResult(
                task_id=task.task_id,
                success=True,
                output=output,
                duration_seconds=time.monotonic() - t0,
            )

        except asyncio.TimeoutError:
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                duration_seconds=time.monotonic() - t0,
                error=f"Task timed out after {effective_timeout}s",
            )
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                duration_seconds=time.monotonic() - t0,
                error=str(exc),
            )

    async def execute_batch(
        self,
        tasks: list[SubTask],
        tool_registry: Any = None,
        parallel: bool = True,
    ) -> list[ExecutionResult]:
        """Execute multiple tasks, optionally in parallel."""
        if parallel:
            return list(
                await asyncio.gather(
                    *(self.execute(t, tool_registry) for t in tasks)
                )
            )
        results: list[ExecutionResult] = []
        for task in tasks:
            results.append(await self.execute(task, tool_registry))
        return results

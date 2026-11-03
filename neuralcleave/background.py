"""Helpers for fire-and-forget asyncio tasks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# The event loop only keeps weak references to tasks, so a task that nobody
# references can be garbage-collected before it finishes. Hold strong
# references here until each task completes.
_background_tasks: set[asyncio.Task[Any]] = set()


def _on_done(task: asyncio.Task[Any]) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("background task %r failed: %r", task.get_name(), exc, exc_info=exc)


def spawn_background(
    coro: Coroutine[Any, Any, Any],
    *,
    loop: asyncio.AbstractEventLoop | None = None,
    name: str | None = None,
) -> asyncio.Task[Any]:
    """Schedule ``coro`` and keep a strong reference until it completes.

    Unhandled exceptions are logged instead of surfacing as
    "Task exception was never retrieved" at interpreter shutdown.
    """
    task = loop.create_task(coro, name=name) if loop is not None else asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_on_done)
    return task

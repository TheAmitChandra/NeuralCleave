"""Structured Logging — NeuralCleave observability layer.

Builds on structlog to provide:

    configure_logging()   — call once at startup to wire up structlog + stdlib
    get_logger(name)      — return a bound structlog logger with service context
    LogBuffer             — in-memory ring buffer of recent log entries (queryable)
    LogEntry              — dataclass representing a single structured log record
    get_log_buffer()      — process-level LogBuffer singleton

The ``LogBuffer`` enables the Observability API endpoint
(``GET /api/v1/observability/logs``) to return recent logs without
requiring a centralised log aggregation backend during development.

Usage::

    configure_logging()   # once in app startup

    log = get_logger("memory.retrieval")
    log.info("retrieval.complete", tier="qdrant", results=12)

    # Query recent WARNING+ logs
    buf = get_log_buffer()
    warnings = buf.query(min_level="WARNING", limit=20)
"""

from __future__ import annotations

import logging
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any

import structlog

# ---------------------------------------------------------------------------
# Enums and data classes
# ---------------------------------------------------------------------------


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @classmethod
    def rank(cls, level: str) -> int:
        _order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        return _order.get(level.upper(), 1)


@dataclass
class LogEntry:
    """A single structured log record stored in the ``LogBuffer``."""

    level: str
    message: str
    logger_name: str
    timestamp: datetime
    trace_id: str = ""
    span_id: str = ""
    agent_id: str = ""
    workflow_id: str = ""
    task_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "message": self.message,
            "logger": self.logger_name,
            "timestamp": self.timestamp.isoformat(),
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "agent_id": self.agent_id,
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            **self.extra,
        }


# ---------------------------------------------------------------------------
# Log buffer
# ---------------------------------------------------------------------------


class LogBuffer:
    """Thread-safe in-memory ring buffer of recent ``LogEntry`` objects.

    Parameters:
        maxlen: Maximum number of entries to keep (oldest are evicted).
    """

    def __init__(self, maxlen: int = 1000) -> None:
        self._buf: deque[LogEntry] = deque(maxlen=maxlen)
        self._lock = Lock()

    def append(self, entry: LogEntry) -> None:
        with self._lock:
            self._buf.append(entry)

    def query(
        self,
        *,
        min_level: str = "DEBUG",
        logger_name: str | None = None,
        agent_id: str | None = None,
        workflow_id: str | None = None,
        limit: int = 100,
    ) -> list[LogEntry]:
        """Return recent entries matching the given filters (newest last)."""
        min_rank = LogLevel.rank(min_level)
        with self._lock:
            results = [
                e
                for e in self._buf
                if LogLevel.rank(e.level) >= min_rank
                and (logger_name is None or e.logger_name == logger_name)
                and (agent_id is None or e.agent_id == agent_id)
                and (workflow_id is None or e.workflow_id == workflow_id)
            ]
        return results[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)


# ---------------------------------------------------------------------------
# Buffer processor (feeds structlog events into LogBuffer)
# ---------------------------------------------------------------------------


class _BufferProcessor:
    """structlog processor that copies each event into the ``LogBuffer``."""

    def __init__(self, buffer: LogBuffer) -> None:
        self._buffer = buffer

    def __call__(self, logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        level = event_dict.get("level", method).upper()
        entry = LogEntry(
            level=level,
            message=str(event_dict.get("event", "")),
            logger_name=str(event_dict.get("logger", "")),
            timestamp=datetime.now(tz=timezone.utc),
            trace_id=str(event_dict.get("trace_id", "")),
            span_id=str(event_dict.get("span_id", "")),
            agent_id=str(event_dict.get("agent_id", "")),
            workflow_id=str(event_dict.get("workflow_id", "")),
            task_id=str(event_dict.get("task_id", "")),
            extra={
                k: v
                for k, v in event_dict.items()
                if k
                not in {
                    "level",
                    "event",
                    "logger",
                    "timestamp",
                    "trace_id",
                    "span_id",
                    "agent_id",
                    "workflow_id",
                    "task_id",
                }
            },
        )
        self._buffer.append(entry)
        return event_dict


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_LOG_BUFFER: LogBuffer | None = None


def get_log_buffer() -> LogBuffer:
    """Return the process-level LogBuffer singleton."""
    global _LOG_BUFFER
    if _LOG_BUFFER is None:
        _LOG_BUFFER = LogBuffer()
    return _LOG_BUFFER


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_LOGGING_CONFIGURED = False


def configure_logging(*, log_level: str = "INFO", app_env: str = "production") -> None:
    """Configure structlog + stdlib logging.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    try:
        from app.config import get_settings

        settings = get_settings()
        log_level = getattr(settings, "LOG_LEVEL", log_level).upper()
        app_env = getattr(settings, "APP_ENV", app_env)
    except Exception:
        pass

    _level = getattr(logging, log_level, logging.INFO)
    buffer = get_log_buffer()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _BufferProcessor(buffer),
    ]

    if app_env in ("development", "test"):
        renderer: Any = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(_level)

    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _LOGGING_CONFIGURED = True


def get_logger(name: str, **bindings: Any) -> Any:
    """Return a structlog bound logger with the given context bindings.

    Bindings become permanent fields in every log event emitted by
    the returned logger (e.g. agent_id, workflow_id).
    """
    log = structlog.get_logger(name)
    if bindings:
        log = log.bind(**bindings)
    return log

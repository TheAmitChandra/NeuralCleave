"""Structured logging setup for CortexFlow.

Configures Python's logging to emit JSON-structured records so that log
aggregators (Loki, CloudWatch, Datadog, etc.) can index fields directly.

In development/TTY mode the formatter falls back to a coloured human-readable
format via rich.logging.RichHandler if the ``rich`` package is available.

Usage::

    from cortexflow.observability.logs import configure_logging

    configure_logging(level="INFO")   # call once at startup

    import logging
    logger = logging.getLogger(__name__)
    logger.info("gateway.started port=%d", 7432)
    # → {"timestamp": "...", "level": "INFO", "logger": "...", "message": "gateway.started port=7432"}
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # Forward any extra fields set via logger.info("...", extra={"key": "val"})
        _skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        for key, val in record.__dict__.items():
            if key not in _skip and not key.startswith("_"):
                payload[key] = val

        return json.dumps(payload, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def configure_logging(
    level: str | int = "INFO",
    *,
    json_output: bool | None = None,
    logger_name: str = "cortexflow",
) -> None:
    """Configure structured logging for CortexFlow.

    Args:
        level:        Log level name or int (e.g. "DEBUG", logging.INFO).
        json_output:  True → always JSON; False → always human; None → auto
                      (JSON when not attached to a TTY, human otherwise).
        logger_name:  Root logger to configure. Defaults to "cortexflow".
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger(logger_name)
    root.setLevel(level)

    # Avoid adding duplicate handlers on repeated calls
    if root.handlers:
        return

    use_json = json_output if json_output is not None else not sys.stderr.isatty()

    if use_json:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
    else:
        try:
            from rich.logging import RichHandler  # type: ignore[import]

            handler = RichHandler(
                show_path=False,
                rich_tracebacks=True,
                markup=False,
            )
        except ImportError:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
                    datefmt="%H:%M:%S",
                )
            )

    root.addHandler(handler)
    root.propagate = False


# ---------------------------------------------------------------------------
# Contextual log adapter
# ---------------------------------------------------------------------------


class ContextLogger:
    """Wraps a standard logger with persistent extra context fields.

    Useful for attaching channel/session context to every log line
    without passing it explicitly each time.

    Usage::

        log = ContextLogger("cortexflow.gateway", channel="telegram", session_id="abc")
        log.info("message.received sender=%s", sender_id)
        # → {"logger": "cortexflow.gateway", "channel": "telegram", "session_id": "abc", ...}
    """

    def __init__(self, name: str, **context: Any) -> None:
        self._logger = logging.getLogger(name)
        self._ctx = context

    def _log(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        extra = {**self._ctx, **kwargs.pop("extra", {})}
        self._logger.log(level, msg, *args, extra=extra, **kwargs)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)

    def bind(self, **extra: Any) -> "ContextLogger":
        """Return a new ContextLogger with additional context fields."""
        return ContextLogger(self._logger.name, **{**self._ctx, **extra})

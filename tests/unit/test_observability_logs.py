"""Unit tests for cortexflow.observability.logs."""

from __future__ import annotations

import json
import logging

import pytest

from cortexflow.observability.logs import (
    ContextLogger,
    JsonFormatter,
    configure_logging,
)


# ---------------------------------------------------------------------------
# JsonFormatter
# ---------------------------------------------------------------------------


def _make_record(
    name: str = "test.logger",
    level: int = logging.INFO,
    msg: str = "hello world",
    **extra,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return record


def test_json_formatter_produces_valid_json() -> None:
    fmt = JsonFormatter()
    record = _make_record()
    output = fmt.format(record)
    data = json.loads(output)
    assert isinstance(data, dict)


def test_json_formatter_contains_required_fields() -> None:
    fmt = JsonFormatter()
    data = json.loads(fmt.format(_make_record(msg="test message")))
    assert "timestamp" in data
    assert "level" in data
    assert "logger" in data
    assert "message" in data


def test_json_formatter_message_correct() -> None:
    fmt = JsonFormatter()
    data = json.loads(fmt.format(_make_record(msg="ping")))
    assert data["message"] == "ping"


def test_json_formatter_level_correct() -> None:
    fmt = JsonFormatter()
    data = json.loads(fmt.format(_make_record(level=logging.WARNING, msg="warn")))
    assert data["level"] == "WARNING"


def test_json_formatter_logger_correct() -> None:
    fmt = JsonFormatter()
    data = json.loads(fmt.format(_make_record(name="cortexflow.gateway")))
    assert data["logger"] == "cortexflow.gateway"


def test_json_formatter_extra_fields_included() -> None:
    fmt = JsonFormatter()
    record = _make_record(msg="with extra")
    record.channel = "telegram"
    record.session_id = "abc123"
    data = json.loads(fmt.format(record))
    assert data.get("channel") == "telegram"
    assert data.get("session_id") == "abc123"


def test_json_formatter_timestamp_format() -> None:
    fmt = JsonFormatter()
    data = json.loads(fmt.format(_make_record()))
    ts = data["timestamp"]
    # ISO 8601 UTC: "2026-06-07T12:00:00Z"
    assert "T" in ts and ts.endswith("Z")


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


def test_configure_logging_sets_level() -> None:
    root = logging.getLogger("cf_test_level")
    root.handlers.clear()
    configure_logging(level="DEBUG", logger_name="cf_test_level", json_output=True)
    assert root.level == logging.DEBUG


def test_configure_logging_does_not_duplicate_handlers() -> None:
    name = "cf_test_dedup"
    root = logging.getLogger(name)
    root.handlers.clear()
    configure_logging(level="INFO", logger_name=name, json_output=True)
    configure_logging(level="INFO", logger_name=name, json_output=True)
    assert len(root.handlers) == 1


# ---------------------------------------------------------------------------
# ContextLogger
# ---------------------------------------------------------------------------


def test_context_logger_forwards_to_underlying_logger(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="cortexflow.ctx_test"):
        ctx_log = ContextLogger("cortexflow.ctx_test", channel="discord")
        ctx_log.info("test message")
    assert "test message" in caplog.text


def test_context_logger_bind_creates_new_logger() -> None:
    ctx1 = ContextLogger("cortexflow.bind_test", channel="telegram")
    ctx2 = ctx1.bind(session_id="xyz")
    assert ctx2._ctx.get("channel") == "telegram"
    assert ctx2._ctx.get("session_id") == "xyz"
    assert ctx1._ctx.get("session_id") is None  # original unchanged


def test_context_logger_bind_does_not_mutate_original() -> None:
    ctx = ContextLogger("cortexflow.mut_test", a=1)
    ctx.bind(b=2)
    assert "b" not in ctx._ctx

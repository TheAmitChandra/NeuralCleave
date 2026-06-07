"""OpenTelemetry Distributed Tracing — CortexFlow observability layer.

All OTel imports are guarded by a ``OTEL_AVAILABLE`` flag so this module
imports cleanly in environments without the ``opentelemetry-sdk`` package.

Features
────────
    setup_tracing(app)    — configure TracerProvider + FastAPI instrumentation
    get_tracer(name)      — retrieve a named tracer
    traced_operation()    — async context manager that creates and closes a span
    TracingContext        — immutable carrier for trace/span IDs
    inject_context()      — inject W3C trace context into outgoing headers
    extract_context()     — extract W3C trace context from incoming headers

Usage::

    async with traced_operation("memory.retrieve", attributes={"tier": "qdrant"}):
        results = await qdrant.search(...)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Lazy OTel import
# ---------------------------------------------------------------------------

try:
    from opentelemetry import context as otel_context
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.propagate import extract as otel_extract
    from opentelemetry.propagate import inject as otel_inject
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    OTEL_AVAILABLE = False
    trace = otel_context = OTLPSpanExporter = FastAPIInstrumentor = None  # type: ignore[assignment]
    otel_inject = otel_extract = None  # type: ignore[assignment]
    SERVICE_NAME = Resource = TracerProvider = None  # type: ignore[assignment]
    BatchSpanProcessor = ConsoleSpanExporter = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TracingContext:
    """Immutable snapshot of the current trace/span IDs.

    When OTel is unavailable, both fields are empty strings.
    """

    trace_id: str = ""
    span_id: str = ""
    is_sampled: bool = False
    baggage: dict[str, str] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return bool(self.trace_id and self.span_id)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

_PROVIDER_INITIALISED = False


def setup_tracing(app: object, *, service_name: str = "cortexflow") -> None:
    """Configure the global TracerProvider and instrument FastAPI.

    Safe to call multiple times — subsequent calls after the first
    are no-ops.
    """
    global _PROVIDER_INITIALISED
    if _PROVIDER_INITIALISED:
        return

    if not OTEL_AVAILABLE:
        logger.warning("tracing.otel_unavailable")
        return

    try:
        from app.config import get_settings

        settings = get_settings()
        _svc_name = getattr(settings, "APP_NAME", service_name)
        _env = getattr(settings, "APP_ENV", "production")
    except Exception:
        _svc_name = service_name
        _env = "production"

    resource = Resource(attributes={SERVICE_NAME: _svc_name})
    provider = TracerProvider(resource=resource)

    if _env in ("development", "test"):
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        try:
            from app.config import get_settings

            settings = get_settings()
            endpoint = getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        except Exception:
            logger.exception("tracing.otlp_setup_failed")
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    if app is not None:
        try:
            FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
        except Exception:
            logger.exception("tracing.fastapi_instrument_failed")

    _PROVIDER_INITIALISED = True
    logger.info("tracing.configured", service_name=_svc_name)


# ---------------------------------------------------------------------------
# Tracer access
# ---------------------------------------------------------------------------


def get_tracer(name: str) -> Any:
    """Return a named tracer. Returns a no-op tracer when OTel is unavailable."""
    if not OTEL_AVAILABLE:
        return _NoopTracer()
    return trace.get_tracer(name)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def traced_operation(
    operation_name: str,
    *,
    attributes: dict[str, Any] | None = None,
    tracer_name: str = "cortexflow",
) -> AsyncGenerator["Any", None]:
    """Async context manager that wraps a block in an OTel span.

    Usage::

        async with traced_operation("tool.execute", attributes={"tool": "shell"}):
            await run_tool()
    """
    if not OTEL_AVAILABLE:
        yield None
        return

    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(operation_name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, str(v))
        yield span


# ---------------------------------------------------------------------------
# Context propagation helpers
# ---------------------------------------------------------------------------


def get_current_context() -> TracingContext:
    """Capture the current OTel trace/span IDs as a ``TracingContext``."""
    if not OTEL_AVAILABLE:
        return TracingContext()
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx is None or not ctx.is_valid:
        return TracingContext()
    return TracingContext(
        trace_id=format(ctx.trace_id, "032x"),
        span_id=format(ctx.span_id, "016x"),
        is_sampled=ctx.trace_flags.sampled,
    )


def inject_context(headers: dict[str, str]) -> dict[str, str]:
    """Inject W3C traceparent/tracestate into an outgoing headers dict.

    Mutates and returns the dict for chaining.
    """
    if not OTEL_AVAILABLE or otel_inject is None:
        return headers
    otel_inject(headers)
    return headers


def extract_context(headers: dict[str, str]) -> Any:
    """Extract OTel context from incoming request headers."""
    if not OTEL_AVAILABLE or otel_extract is None:
        return None
    return otel_extract(headers)


# ---------------------------------------------------------------------------
# No-op tracer stub
# ---------------------------------------------------------------------------


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def get_span_context(self) -> None:
        return None


class _NoopTracer:
    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoopSpan:
        return _NoopSpan()

"""CortexFlow — FastAPI application entry point."""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.v1 import agents, approvals, auth, events, mcp, memory, observability, tools, workflows
from app.api.websocket import router as ws_router
from app.config import get_settings
from app.core.observability.logs import configure_logging
from app.core.observability.metrics import setup_metrics
from app.core.observability.tracing import setup_tracing
from app.db.neo4j import close_neo4j, init_neo4j
from app.db.postgres import close_db, init_db
from app.db.qdrant import close_qdrant, init_qdrant
from app.db.redis import close_redis, init_redis

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    configure_logging()
    logger.info("CortexFlow starting", env=settings.APP_ENV)

    # Initialise all database connections
    await init_db()
    await init_redis()
    await init_qdrant()
    await init_neo4j()

    # Observability
    setup_tracing(app)
    setup_metrics()

    # Preload the sentence-transformers embedding model in a thread pool so the
    # first /memory/search or /memory/store request does not block for 3-5s (BUG-007).
    try:
        import asyncio

        from sentence_transformers import SentenceTransformer

        import app.api.v1.memory as memory_module

        loop = asyncio.get_running_loop()
        memory_module._EMBEDDING_MODEL = await loop.run_in_executor(
            None, lambda: SentenceTransformer("all-MiniLM-L6-v2")
        )
        logger.info("embedding_model_loaded")
    except ImportError:
        logger.warning("sentence_transformers_not_available")
    except Exception as exc:
        logger.warning("embedding_model_load_failed", error=str(exc))

    logger.info("CortexFlow ready")
    yield

    # Graceful shutdown
    logger.info("CortexFlow shutting down")
    await close_db()
    await close_redis()
    await close_qdrant()
    await close_neo4j()
    logger.info("CortexFlow shutdown complete")


# ── Rate limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)

# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="CortexFlow",
    description="Autonomous Cognitive Operating System — API",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Log every request with latency and trace context."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        client=request.client.host if request.client else "unknown",
    )
    return response


# ── Routers ───────────────────────────────────────────────────────────────────
PREFIX = settings.API_V1_PREFIX

app.include_router(auth.router, prefix=PREFIX, tags=["auth"])
app.include_router(agents.router, prefix=PREFIX, tags=["agents"])
app.include_router(workflows.router, prefix=PREFIX, tags=["workflows"])
app.include_router(memory.router, prefix=PREFIX, tags=["memory"])
app.include_router(tools.router, prefix=PREFIX, tags=["tools"])
app.include_router(events.router, prefix=PREFIX, tags=["events"])
app.include_router(observability.router, prefix=PREFIX, tags=["observability"])
app.include_router(approvals.router, prefix=PREFIX, tags=["approvals"])
app.include_router(mcp.router, tags=["mcp"])  # MCP at /mcp/ (no versioned prefix)
app.include_router(ws_router, tags=["websocket"])


# ── Health endpoints ───────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health_check() -> JSONResponse:
    """Liveness probe — returns 200 if process is running."""
    return JSONResponse({"status": "ok", "service": "cortexflow"})


@app.get("/ready", tags=["health"])
async def readiness_check() -> JSONResponse:
    """Readiness probe — verifies DB connectivity before serving traffic."""
    from app.db.postgres import check_db_health
    from app.db.redis import check_redis_health

    checks = {
        "postgres": await check_db_health(),
        "redis": await check_redis_health(),
    }
    all_healthy = all(checks.values())
    return JSONResponse(
        {"status": "ready" if all_healthy else "degraded", "checks": checks},
        status_code=200 if all_healthy else 503,
    )

"""CortexFlow Gateway — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cortexflow_ai import __version__
from cortexflow_ai.canvas.routes import api_router as canvas_api_router
from cortexflow_ai.canvas.routes import page_router as canvas_page_router
from cortexflow_ai.canvas.routes import set_canvas_renderer
from cortexflow_ai.config import CortexFlowConfig, load_config
from cortexflow_ai.gateway.routes import router as api_router
from cortexflow_ai.gateway.routes import set_runtime
from cortexflow_ai.gateway.terminal import router as terminal_router
from cortexflow_ai.gateway.websocket import get_manager
from cortexflow_ai.gateway.websocket import router as ws_router
from cortexflow_ai.pwa.routes import push_router, pwa_router

logger = logging.getLogger(__name__)


def _build_lifespan(cfg: CortexFlowConfig):
    """Create a lifespan context manager bound to *cfg*.

    On startup it builds the AgentRuntime, connects channels, and registers
    the runtime with the REST + WebSocket layers via set_runtime(). On
    shutdown it tears everything down. Runtime construction is wrapped so a
    misconfiguration cannot prevent the gateway from serving /health.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[type-arg]
        from cortexflow_ai.canvas.renderer import CanvasRenderer
        from cortexflow_ai.scheduler import HeartbeatScheduler

        manager = get_manager()
        await manager.start()

        canvas = CanvasRenderer()
        set_canvas_renderer(canvas)
        app.state.canvas = canvas

        scheduler = HeartbeatScheduler()
        app.state.scheduler = scheduler
        await scheduler.start()

        runtime = None
        try:
            from cortexflow_ai.agent.runtime import AgentRuntime

            runtime = AgentRuntime.from_config(cfg)
            await runtime.start()
            set_runtime(runtime)
            app.state.runtime = runtime
            logger.info("CortexFlow Gateway v2 started with AgentRuntime")
        except Exception as exc:
            logger.error("runtime startup failed (%s) — serving without agent", exc)
            app.state.runtime = None

        try:
            yield
        finally:
            await scheduler.stop()
            if runtime is not None:
                try:
                    await runtime.stop()
                except Exception as exc:
                    logger.warning("runtime shutdown error: %s", exc)
            set_runtime(None)
            set_canvas_renderer(None)
            await manager.stop()
            logger.info("CortexFlow Gateway v2 stopped")

    return lifespan


def create_app(config: CortexFlowConfig | None = None) -> FastAPI:
    """Build and return the FastAPI application."""
    cfg = config or load_config()

    app = FastAPI(
        title="CortexFlow Gateway",
        description="Personal AI Assistant — WebSocket + REST API",
        version=__version__,
        lifespan=_build_lifespan(cfg),
    )

    app.add_middleware(
        CORSMiddleware,
        # Tauri v2 on Windows (WebView2) serves the bundled frontend from the
        # app identifier as a virtual hostname: https://ai.cortexflow.desktop.
        # macOS/Linux use the tauri:// custom-protocol scheme instead.
        # Tauri v1 Windows used https://tauri.localhost (kept for completeness).
        # The regex additionally covers any localhost port for the dev server.
        allow_origins=[
            f"http://localhost:{cfg.ui.web_port}",
            f"http://127.0.0.1:{cfg.ui.web_port}",
            "https://ai.cortexflow.desktop",  # Tauri v2 Windows (WebView2 virtual host)
            "https://tauri.localhost",         # Tauri v1 Windows
            "tauri://localhost",               # Tauri v2 macOS/Linux
        ],
        allow_origin_regex=r"https?://localhost(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Optional REST API key — only enforced when gateway.api_key is non-empty.
    # WebSocket routes and /health are exempt (WS upgrade ignores headers on
    # most clients; /health is used by Docker and load-balancer probes).
    _api_key = cfg.gateway.api_key
    if _api_key:
        @app.middleware("http")
        async def _enforce_api_key(request: Request, call_next):
            path = request.url.path
            if not path.startswith("/api/") and not path.startswith("/ws/"):
                return await call_next(request)
            if path.startswith("/ws/"):
                return await call_next(request)
            provided = request.headers.get("X-API-Key", "")
            if provided != _api_key:
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
            return await call_next(request)

    app.include_router(ws_router)
    app.include_router(terminal_router)
    app.include_router(api_router)
    app.include_router(canvas_api_router, prefix="/api/v1")
    app.include_router(canvas_page_router)
    app.include_router(pwa_router)
    app.include_router(push_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "gateway": f"{cfg.gateway.bind}:{cfg.gateway.port}",
            "sessions": get_manager().session_count,
        }

    return app


def run(config: CortexFlowConfig | None = None) -> None:
    """Start the gateway server (blocking)."""
    import uvicorn

    cfg = config or load_config()
    app = create_app(cfg)
    uvicorn.run(app, host=cfg.gateway.bind, port=cfg.gateway.port, log_level="info")


if __name__ == "__main__":
    run()

"""CortexFlow Gateway — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cortexflow.config import CortexFlowConfig, load_config
from cortexflow.gateway.routes import router as api_router, set_runtime
from cortexflow.gateway.websocket import get_manager, router as ws_router

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
        manager = get_manager()
        await manager.start()

        runtime = None
        try:
            from cortexflow.agent.runtime import AgentRuntime

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
            if runtime is not None:
                try:
                    await runtime.stop()
                except Exception as exc:
                    logger.warning("runtime shutdown error: %s", exc)
            set_runtime(None)
            await manager.stop()
            logger.info("CortexFlow Gateway v2 stopped")

    return lifespan


def create_app(config: CortexFlowConfig | None = None) -> FastAPI:
    """Build and return the FastAPI application."""
    cfg = config or load_config()

    app = FastAPI(
        title="CortexFlow Gateway",
        description="Personal AI Assistant — WebSocket + REST API",
        version="2.0.0",
        lifespan=_build_lifespan(cfg),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://localhost:{cfg.ui.web_port}",
            f"http://127.0.0.1:{cfg.ui.web_port}",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ws_router)
    app.include_router(api_router)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "2.0.0",
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

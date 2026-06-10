"""CortexFlow Gateway — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cortexflow.config import CortexFlowConfig, load_config
from cortexflow.gateway.routes import router as api_router
from cortexflow.gateway.websocket import get_manager, router as ws_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    manager = get_manager()
    await manager.start()
    logger.info("CortexFlow Gateway v2 started")
    yield
    await manager.stop()
    logger.info("CortexFlow Gateway v2 stopped")


def create_app(config: CortexFlowConfig | None = None) -> FastAPI:
    """Build and return the FastAPI application."""
    cfg = config or load_config()

    app = FastAPI(
        title="CortexFlow Gateway",
        description="Personal AI Assistant — WebSocket + REST API",
        version="2.0.0",
        lifespan=lifespan,
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

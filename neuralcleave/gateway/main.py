"""NeuralCleave Gateway — FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from neuralcleave import __version__
from neuralcleave.canvas.routes import api_router as canvas_api_router
from neuralcleave.canvas.routes import page_router as canvas_page_router
from neuralcleave.canvas.routes import set_canvas_renderer
from neuralcleave.config import NeuralCleaveConfig, load_config
from neuralcleave.gateway.origin_check import (
    ORIGIN_REGEX,
    allowed_origins,
    set_allowed_origins,
)
from neuralcleave.gateway.routes import (
    get_init_phase,
    get_runtime,
    set_hub_installer,
    set_init_phase,
    set_orchestrator,
    set_plugin_registry,
    set_runtime,
)
from neuralcleave.gateway.routes import (
    router as api_router,
)
from neuralcleave.gateway.terminal import router as terminal_router
from neuralcleave.gateway.websocket import get_manager
from neuralcleave.gateway.websocket import router as ws_router
from neuralcleave.pwa.routes import push_router, pwa_router

logger = logging.getLogger(__name__)


def _build_lifespan(cfg: NeuralCleaveConfig):
    """Create a lifespan context manager bound to *cfg*.

    On startup it builds the AgentRuntime, connects channels, and registers
    the runtime with the REST + WebSocket layers via set_runtime(). On
    shutdown it tears everything down. Runtime construction is wrapped so a
    misconfiguration cannot prevent the gateway from serving /health.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[type-arg]
        from neuralcleave.canvas.renderer import CanvasRenderer
        from neuralcleave.gateway.config_watcher import ConfigWatcher
        from neuralcleave.scheduler import HeartbeatScheduler

        manager = get_manager()
        await manager.start()

        canvas = CanvasRenderer()
        set_canvas_renderer(canvas)
        app.state.canvas = canvas

        scheduler = HeartbeatScheduler()
        app.state.scheduler = scheduler
        await scheduler.start()

        async def _on_config_reload(fresh_cfg: NeuralCleaveConfig) -> None:
            """Apply the parts of a reloaded config that are safe to mutate
            on a live singleton without rebuilding the whole pipeline.

            Model settings/API keys are NOT applied here despite the log
            line that used to claim otherwise — ModelRouter has no live
            "re-key" path today (its provider keys are constructor-only), so
            actually honoring that claim needs router surgery out of scope
            for a config-watcher callback. [security] genuinely can be
            applied live, reusing the same POLICY/tool-registry mutation
            the /api/v1/approvals/policy POST route already does, so this
            does exactly that instead of only logging that it would.
            """
            from neuralcleave.gateway.routes import _set_live_require_shell_approval
            from neuralcleave.tools.approval_policy import POLICY

            POLICY.security = fresh_cfg.security.security_mode
            POLICY.ask = fresh_cfg.security.ask_mode
            _set_live_require_shell_approval(fresh_cfg.security.require_shell_approval)
            logger.info(
                "gateway: applied reloaded [security] config "
                "(require_shell_approval=%s security_mode=%s ask_mode=%s); "
                "model/API-key settings still require a restart",
                fresh_cfg.security.require_shell_approval,
                fresh_cfg.security.security_mode,
                fresh_cfg.security.ask_mode,
            )

        config_watcher = ConfigWatcher(cfg, on_reload=_on_config_reload)
        await config_watcher.start()
        app.state.config_watcher = config_watcher

        # Heavy init (AgentRuntime + plugins) runs as a background task so
        # the server yields immediately and /api/v1/status responds from the
        # first poll.  The frontend reads runtime_available + init_phase to
        # show meaningful progress labels instead of "Checking…".
        app.state.runtime = None
        set_init_phase("runtime")

        async def _init_runtime() -> None:
            rt = None
            try:
                from neuralcleave.agent.runtime import AgentRuntime

                rt = AgentRuntime.from_config(cfg)
                await rt.start()
                set_runtime(rt)
                app.state.runtime = rt
                logger.info("NeuralCleave Gateway v2 started with AgentRuntime")
            except Exception as exc:
                logger.error("runtime startup failed (%s) — serving without agent", exc)

            try:
                from neuralcleave.orchestrator.orchestrator import AgentOrchestrator

                # Sharing the runtime's own ModelRouter here (rather than
                # leaving router=None) is what actually lets a routed task
                # generate a real response — without it, route() falls back
                # to its placeholder-only mode regardless of how many nodes
                # are registered against this same orchestrator instance.
                router = getattr(getattr(rt, "_pipeline", None), "_router", None)
                orchestrator = AgentOrchestrator(router=router)
                set_orchestrator(orchestrator)
                app.state.orchestrator = orchestrator
                logger.info("AgentOrchestrator wired successfully")
            except Exception as exc:
                logger.error("orchestrator startup failed (%s) — /orchestrator endpoints unavailable", exc)

            # Wire plugin registry and hub installer after runtime so a
            # plugin-load failure never prevents the agent from starting.
            # Sharing the runtime's own ToolRegistry here (rather than
            # letting PluginRegistry default to None) is what actually lets
            # hub-installed and self-written-skill tools reach the live
            # agent — without it, plugin/skill registration silently never
            # became callable by the LLM.
            set_init_phase("plugins")
            try:
                from neuralcleave.hub.installer import HubInstaller
                from neuralcleave.plugins.registry import PluginRegistry

                tool_registry = getattr(getattr(rt, "_pipeline", None), "_tool_registry", None)
                plugin_registry = PluginRegistry(tool_registry)
                plugin_registry.discover()
                await plugin_registry.load_all()
                set_plugin_registry(plugin_registry)

                hub_installer = HubInstaller(plugin_registry=plugin_registry)
                set_hub_installer(hub_installer)
                logger.info("PluginRegistry and HubInstaller wired successfully")
            except Exception as exc:
                logger.error("plugin/hub startup failed (%s) — serving without plugins", exc)

            # Register at least one real job with the heartbeat scheduler.
            # Before this, HeartbeatScheduler ran forever with an empty
            # task dict in every gateway boot (round 5 gap analysis P2,
            # 2026-08-21) — the whole cron/interval engine was real and
            # well-tested in isolation, but nothing outside its own
            # docstring example ever called add_task().
            if rt is not None and getattr(rt, "_long_term", None) is not None:
                try:
                    from neuralcleave.memory.archiver import SessionArchiver
                    from neuralcleave.scheduler import ScheduledTask

                    archiver = SessionArchiver(long_term=rt._long_term, router=rt._pipeline._router)

                    async def _run_memory_archival() -> None:
                        archived = await archiver.archive_inactive_sessions(older_than_days=30)
                        if archived:
                            logger.info("scheduler: archived %d inactive session(s)", len(archived))

                    scheduler.add_task(ScheduledTask(
                        name="memory_archival",
                        handler=_run_memory_archival,
                        cron="0 3 * * *",  # 03:00 daily
                    ))
                    logger.info("scheduler: registered memory_archival task")
                except Exception as exc:
                    logger.error("scheduler: failed to register memory_archival task (%s)", exc)

            # Only report "ready" when the runtime actually exists — before
            # this, the phase flipped to "ready" unconditionally even when
            # AgentRuntime.from_config() raised and rt stayed None, so
            # /ready reported ready=true for a gateway with no working
            # pipeline at all.
            set_init_phase("ready" if rt is not None else "runtime_failed")

        init_task = asyncio.create_task(_init_runtime())
        app.state.init_task = init_task

        try:
            yield
        finally:
            await config_watcher.stop()
            await scheduler.stop()

            if not init_task.done():
                init_task.cancel()
                try:
                    await init_task
                except asyncio.CancelledError:
                    pass

            rt = app.state.runtime
            if rt is not None:
                try:
                    await rt.stop()
                except Exception as exc:
                    logger.warning("runtime shutdown error: %s", exc)

            set_init_phase("starting")
            set_runtime(None)
            set_orchestrator(None)
            set_plugin_registry(None)
            set_hub_installer(None)
            set_canvas_renderer(None)
            await manager.stop()
            logger.info("NeuralCleave Gateway v2 stopped")

    return lifespan


def create_app(config: NeuralCleaveConfig | None = None) -> FastAPI:
    """Build and return the FastAPI application."""
    cfg = config or load_config()

    app = FastAPI(
        title="NeuralCleave Gateway",
        description="Personal AI Assistant — WebSocket + REST API",
        version=__version__,
        lifespan=_build_lifespan(cfg),
    )

    # Populates the allow-list neuralcleave.gateway.origin_check.is_allowed_origin()
    # consults — the *only* real origin restriction any /ws/* route gets,
    # since CORSMiddleware below never applies to WebSocket scope at all.
    set_allowed_origins(cfg)

    app.add_middleware(
        CORSMiddleware,
        # Tauri v2.11+ on Windows uses http://tauri.localhost (HTTP, not HTTPS)
        # as the WebView2 virtual host origin. Older Tauri v2 used
        # https://com.neuralcleave.desktop (identifier-based). Both are kept.
        # macOS/Linux use the tauri:// custom-protocol scheme instead.
        # The regex covers any localhost/tauri.localhost port for the dev server.
        allow_origins=allowed_origins(cfg),
        allow_origin_regex=ORIGIN_REGEX.pattern,
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

    @app.get("/ready")
    async def ready(response: Response) -> dict[str, Any]:
        """Readiness probe — 200 once startup has fully completed AND the
        runtime is actually usable, 503 otherwise. Distinct from /health
        (always 200 once the process is up), for orchestrators that gate
        traffic admission on readiness rather than mere liveness.

        Deliberately does not make a live network call to any LLM provider
        (that would make a frequently-polled endpoint slow and flaky) — a
        total provider/router construction failure already surfaces via the
        "runtime" check below, since ModelRouter.from_config() is the first
        thing AgentRuntime.from_config() does.
        """
        phase = get_init_phase()
        runtime = get_runtime()
        checks: dict[str, bool] = {
            "phase": phase == "ready",
            "runtime": runtime is not None,
        }
        adapters = getattr(runtime, "_adapters", None) or {}
        if adapters:
            checks["channel_connected"] = any(a.is_connected for a in adapters.values())
        is_ready = all(checks.values())
        response.status_code = 200 if is_ready else 503
        return {"ready": is_ready, "phase": phase, "checks": checks}

    return app


def run(config: NeuralCleaveConfig | None = None) -> None:
    """Start the gateway server (blocking)."""
    import uvicorn

    cfg = config or load_config()
    app = create_app(cfg)
    uvicorn.run(app, host=cfg.gateway.bind, port=cfg.gateway.port, log_level="info")


if __name__ == "__main__":
    run()

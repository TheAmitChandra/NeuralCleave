"""Unit tests for cortexflow.gateway.main — create_app(), lifespan, run()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from cortexflow_ai.agent.runtime import AgentRuntime
from cortexflow_ai.config import CortexFlowConfig
from cortexflow_ai.gateway.main import create_app, run
from cortexflow_ai.gateway.routes import get_runtime, set_runtime


@pytest.fixture(autouse=True)
def reset_runtime():
    set_runtime(None)
    yield
    set_runtime(None)


def make_fake_runtime() -> MagicMock:
    runtime = MagicMock()
    runtime.start = AsyncMock()
    runtime.stop = AsyncMock()
    return runtime


# ---------------------------------------------------------------------------
# create_app() — basic construction
# ---------------------------------------------------------------------------


def test_create_app_returns_fastapi_instance():
    app = create_app(CortexFlowConfig())
    assert app.title == "CortexFlow Gateway"
    assert app.version == "2.0.0"


def test_create_app_uses_default_config_when_none_given():
    app = create_app()  # exercises load_config() default path
    assert app.title == "CortexFlow Gateway"


def test_health_endpoint_without_lifespan():
    app = create_app(CortexFlowConfig())
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "2.0.0"
    assert "sessions" in body


# ---------------------------------------------------------------------------
# Lifespan — runtime startup succeeds
# ---------------------------------------------------------------------------


def test_lifespan_runtime_success_sets_state_and_runtime():
    app = create_app(CortexFlowConfig())
    fake_runtime = make_fake_runtime()

    with patch.object(AgentRuntime, "from_config", return_value=fake_runtime):
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert client.app.state.runtime is fake_runtime
            assert get_runtime() is fake_runtime

    fake_runtime.start.assert_awaited_once()
    fake_runtime.stop.assert_awaited_once()
    assert get_runtime() is None


# ---------------------------------------------------------------------------
# Lifespan — runtime startup fails, gateway still serves
# ---------------------------------------------------------------------------


def test_lifespan_runtime_failure_serves_without_agent():
    app = create_app(CortexFlowConfig())

    with patch.object(AgentRuntime, "from_config", side_effect=RuntimeError("bad config")):
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert client.app.state.runtime is None
            assert get_runtime() is None


# ---------------------------------------------------------------------------
# Lifespan — runtime.stop() raising on shutdown doesn't propagate
# ---------------------------------------------------------------------------


def test_lifespan_swallows_runtime_stop_exception():
    app = create_app(CortexFlowConfig())
    fake_runtime = make_fake_runtime()
    fake_runtime.stop = AsyncMock(side_effect=Exception("shutdown error"))

    with patch.object(AgentRuntime, "from_config", return_value=fake_runtime):
        with TestClient(app) as client:
            client.get("/health")
        # exiting the `with` block triggers shutdown; must not raise

    fake_runtime.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# Lifespan — runtime.start() raising is treated like from_config failing
# ---------------------------------------------------------------------------


def test_lifespan_runtime_start_failure_serves_without_agent():
    app = create_app(CortexFlowConfig())
    fake_runtime = make_fake_runtime()
    fake_runtime.start = AsyncMock(side_effect=RuntimeError("channel connect failed"))

    with patch.object(AgentRuntime, "from_config", return_value=fake_runtime):
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert client.app.state.runtime is None


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


def test_run_calls_uvicorn_with_config_bind_and_port():
    cfg = CortexFlowConfig()
    cfg.gateway.bind = "0.0.0.0"
    cfg.gateway.port = 9999

    with patch("uvicorn.run") as mock_uvicorn_run:
        run(cfg)

    mock_uvicorn_run.assert_called_once()
    call_kwargs = mock_uvicorn_run.call_args[1]
    assert call_kwargs["host"] == "0.0.0.0"
    assert call_kwargs["port"] == 9999


def test_run_uses_default_config_when_none_given():
    with patch("uvicorn.run") as mock_uvicorn_run:
        run()

    mock_uvicorn_run.assert_called_once()

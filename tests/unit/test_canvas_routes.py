"""Unit tests for canvas REST endpoints and WebSocket."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import cortexflow_ai.canvas.routes as canvas_routes_module
from cortexflow_ai.canvas.block import CanvasBlock
from cortexflow_ai.canvas.renderer import CanvasRenderer
from cortexflow_ai.canvas.routes import api_router, page_router


@pytest.fixture(autouse=True)
def reset_renderer():
    """Ensure each test starts with a fresh renderer state."""
    canvas_routes_module.set_canvas_renderer(None)
    yield
    canvas_routes_module.set_canvas_renderer(None)


@pytest.fixture()
def app():
    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.include_router(page_router)
    return application


@pytest.fixture()
def renderer():
    r = CanvasRenderer()
    canvas_routes_module.set_canvas_renderer(r)
    return r


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /api/v1/canvas/state
# ---------------------------------------------------------------------------


def test_state_no_renderer(client):
    resp = client.get("/api/v1/canvas/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["blocks"] == []


def test_state_empty_canvas(client, renderer):
    resp = client.get("/api/v1/canvas/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["blocks"] == []
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_state_with_blocks(client, renderer):
    await renderer.add_block(CanvasBlock.new("text", "hello"))
    resp = client.get("/api/v1/canvas/state")
    data = resp.json()
    assert data["count"] == 1
    assert data["blocks"][0]["block_type"] == "text"


# ---------------------------------------------------------------------------
# GET /api/v1/canvas/status
# ---------------------------------------------------------------------------


def test_status_no_renderer(client):
    resp = client.get("/api/v1/canvas/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["block_count"] == 0
    assert data["subscriber_count"] == 0


def test_status_with_renderer(client, renderer):
    resp = client.get("/api/v1/canvas/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["block_count"] == 0


# ---------------------------------------------------------------------------
# POST /api/v1/canvas/render
# ---------------------------------------------------------------------------


def test_render_no_renderer_503(client):
    resp = client.post("/api/v1/canvas/render", json={"block_type": "text", "content": "hi"})
    assert resp.status_code == 503


def test_render_unknown_type_422(client, renderer):
    resp = client.post("/api/v1/canvas/render", json={"block_type": "bad", "content": "x"})
    assert resp.status_code == 422


def test_render_text_success_201(client, renderer):
    resp = client.post(
        "/api/v1/canvas/render",
        json={"block_type": "text", "content": "Hello canvas", "title": "Greeting"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["block_type"] == "text"
    assert data["content"] == "Hello canvas"
    assert data["title"] == "Greeting"
    assert "id" in data


def test_render_markdown_201(client, renderer):
    resp = client.post(
        "/api/v1/canvas/render",
        json={"block_type": "markdown", "content": "# Hello"},
    )
    assert resp.status_code == 201


def test_render_code_201(client, renderer):
    resp = client.post(
        "/api/v1/canvas/render",
        json={"block_type": "code", "content": {"code": "x=1", "language": "python"}},
    )
    assert resp.status_code == 201


def test_render_table_201(client, renderer):
    resp = client.post(
        "/api/v1/canvas/render",
        json={
            "block_type": "table",
            "content": {"headers": ["A", "B"], "rows": [[1, 2]]},
        },
    )
    assert resp.status_code == 201


def test_render_chart_201(client, renderer):
    resp = client.post(
        "/api/v1/canvas/render",
        json={
            "block_type": "chart",
            "content": {"chart_type": "bar", "labels": ["X"], "values": [10]},
        },
    )
    assert resp.status_code == 201


def test_render_image_201(client, renderer):
    resp = client.post(
        "/api/v1/canvas/render",
        json={"block_type": "image", "content": "https://example.com/img.png"},
    )
    assert resp.status_code == 201


def test_render_html_201(client, renderer):
    resp = client.post(
        "/api/v1/canvas/render",
        json={"block_type": "html", "content": "<h1>Hi</h1>"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_render_adds_to_renderer_state(client, renderer):
    client.post(
        "/api/v1/canvas/render",
        json={"block_type": "text", "content": "check state"},
    )
    assert renderer.block_count() == 1


def test_render_returns_block_with_id(client, renderer):
    resp = client.post(
        "/api/v1/canvas/render",
        json={"block_type": "text", "content": "id check"},
    )
    assert len(resp.json()["id"]) == 32


# ---------------------------------------------------------------------------
# DELETE /api/v1/canvas/clear
# ---------------------------------------------------------------------------


def test_clear_no_renderer_503(client):
    resp = client.delete("/api/v1/canvas/clear")
    assert resp.status_code == 503


def test_clear_success_204(client, renderer):
    resp = client.delete("/api/v1/canvas/clear")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_clear_empties_blocks(client, renderer):
    await renderer.add_block(CanvasBlock.new("text", "to clear"))
    client.delete("/api/v1/canvas/clear")
    assert renderer.block_count() == 0


# ---------------------------------------------------------------------------
# GET /canvas  — HTML page
# ---------------------------------------------------------------------------


def test_canvas_page_returns_html(client):
    resp = client.get("/canvas")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_canvas_page_contains_websocket_connect(client):
    resp = client.get("/canvas")
    assert "/ws/canvas" in resp.text


def test_canvas_page_contains_title(client):
    resp = client.get("/canvas")
    assert "CortexFlow Live Canvas" in resp.text


def test_canvas_page_contains_clear_button(client):
    resp = client.get("/canvas")
    assert "clearCanvas" in resp.text or "clear" in resp.text.lower()


# ---------------------------------------------------------------------------
# WebSocket /ws/canvas
# ---------------------------------------------------------------------------


def test_websocket_no_renderer_closes_with_error(app):
    canvas_routes_module.set_canvas_renderer(None)
    client = TestClient(app)
    with client.websocket_connect("/ws/canvas") as ws:
        data = ws.receive_json()
        assert data["type"] == "error"


def test_websocket_connect_receives_state(app, renderer):
    client = TestClient(app)
    with client.websocket_connect("/ws/canvas") as ws:
        data = ws.receive_json()
        assert data["type"] == "state"
        assert "blocks" in data


@pytest.mark.asyncio
async def test_websocket_receives_add_on_block(app, renderer):
    client = TestClient(app)
    with client.websocket_connect("/ws/canvas") as ws:
        # consume initial state
        ws.receive_json()
        # add a block via REST
        client.post(
            "/api/v1/canvas/render",
            json={"block_type": "text", "content": "live update"},
        )
        msg = ws.receive_json()
        assert msg["type"] == "add"
        assert msg["block"]["content"] == "live update"


@pytest.mark.asyncio
async def test_websocket_receives_clear(app, renderer):
    await renderer.add_block(CanvasBlock.new("text", "temp"))
    client = TestClient(app)
    with client.websocket_connect("/ws/canvas") as ws:
        ws.receive_json()  # state
        client.delete("/api/v1/canvas/clear")
        msg = ws.receive_json()
        assert msg["type"] == "clear"


def test_websocket_ping_pong(app, renderer):
    client = TestClient(app)
    with client.websocket_connect("/ws/canvas") as ws:
        ws.receive_json()  # state
        ws.send_text("ping")
        msg = ws.receive_json()
        assert msg["type"] == "pong"

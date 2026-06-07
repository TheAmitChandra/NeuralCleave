"""WebSocket API — real-time agent, workflow, and system event streams.

Endpoints:
    ws://host/ws/agents      — live agent state updates
    ws://host/ws/workflows   — workflow execution progress stream
    ws://host/ws/events      — system event bus stream

Each client receives JSON-encoded messages with the structure:
    {"type": "<event_type>", "data": {...}, "timestamp": "<ISO8601>"}

Authentication: clients must send a valid JWT in the first message
    {"token": "<access_token>"}
or via the `Authorization: Bearer <token>` query parameter.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.config import get_settings
from app.core.security.zero_trust import verify_access_token

logger = structlog.get_logger(__name__)
router = APIRouter()
settings = get_settings()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _msg(event_type: str, data: dict[str, Any]) -> str:
    return json.dumps({"type": event_type, "data": data, "timestamp": _now_iso()})


async def _authenticate_ws(websocket: WebSocket, token: str | None) -> str | None:
    """
    Authenticate a WebSocket connection by verifying the provided JWT.

    Returns the subject (user_id) on success, or None if authentication fails.
    The caller is responsible for closing the socket on failure.
    """
    if not token:
        # Ask client to send token as first message
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            payload = json.loads(raw)
            token = payload.get("token")
        except (asyncio.TimeoutError, json.JSONDecodeError, Exception):  # noqa: BLE001
            return None

    if not token:
        return None

    try:
        user_id = verify_access_token(token)
        return user_id
    except (JWTError, Exception):  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Tracks active WebSocket connections per channel."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    def connect(self, channel: str, ws: WebSocket) -> None:
        self._connections.setdefault(channel, []).append(ws)

    def disconnect(self, channel: str, ws: WebSocket) -> None:
        channel_conns = self._connections.get(channel, [])
        if ws in channel_conns:
            channel_conns.remove(ws)

    async def broadcast(self, channel: str, message: str) -> None:
        """Send *message* to all connected clients on *channel*."""
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(channel, [])):
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(channel, ws)

    def active_count(self, channel: str) -> int:
        return len(self._connections.get(channel, []))


_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Agents WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/ws/agents")
async def ws_agents(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """
    Live agent state stream.

    Broadcasts periodic ``agent.heartbeat`` events for all active agents.
    Clients can send ``{"action": "subscribe", "agent_id": "<id>"}`` to filter
    events to a specific agent.
    """
    await websocket.accept()

    user_id = await _authenticate_ws(websocket, token)
    if not user_id:
        await websocket.send_text(_msg("error", {"detail": "Authentication required"}))
        await websocket.close(code=4001)
        return

    _manager.connect("agents", websocket)
    logger.info("ws_agents_connected", user_id=user_id)

    try:
        await websocket.send_text(_msg("connected", {"channel": "agents", "user_id": user_id}))

        while True:
            # Send a heartbeat every 5 seconds with a placeholder agent state
            await asyncio.sleep(5)
            await websocket.send_text(
                _msg(
                    "agent.heartbeat",
                    {
                        "active_agents": 0,
                        "states": [],
                    },
                )
            )
    except WebSocketDisconnect:
        logger.info("ws_agents_disconnected", user_id=user_id)
    finally:
        _manager.disconnect("agents", websocket)


# ---------------------------------------------------------------------------
# Workflows WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/ws/workflows")
async def ws_workflows(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """
    Workflow execution progress stream.

    Broadcasts ``workflow.state_change`` events whenever a workflow transitions
    between states (PENDING → RUNNING → COMPLETED | FAILED).
    """
    await websocket.accept()

    user_id = await _authenticate_ws(websocket, token)
    if not user_id:
        await websocket.send_text(_msg("error", {"detail": "Authentication required"}))
        await websocket.close(code=4001)
        return

    _manager.connect("workflows", websocket)
    logger.info("ws_workflows_connected", user_id=user_id)

    try:
        await websocket.send_text(_msg("connected", {"channel": "workflows", "user_id": user_id}))

        while True:
            await asyncio.sleep(10)
            await websocket.send_text(
                _msg(
                    "workflow.heartbeat",
                    {
                        "running_workflows": 0,
                        "recent_completions": [],
                    },
                )
            )
    except WebSocketDisconnect:
        logger.info("ws_workflows_disconnected", user_id=user_id)
    finally:
        _manager.disconnect("workflows", websocket)


# ---------------------------------------------------------------------------
# Events WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/ws/events")
async def ws_events(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """
    System event bus stream.

    Forwards all events dispatched by the EventRouter to connected clients.
    This enables the frontend to display live system activity.
    """
    await websocket.accept()

    user_id = await _authenticate_ws(websocket, token)
    if not user_id:
        await websocket.send_text(_msg("error", {"detail": "Authentication required"}))
        await websocket.close(code=4001)
        return

    _manager.connect("events", websocket)
    logger.info("ws_events_connected", user_id=user_id)

    try:
        await websocket.send_text(_msg("connected", {"channel": "events", "user_id": user_id}))

        while True:
            await asyncio.sleep(15)
            await websocket.send_text(
                _msg(
                    "system.heartbeat",
                    {"status": "ok"},
                )
            )
    except WebSocketDisconnect:
        logger.info("ws_events_disconnected", user_id=user_id)
    finally:
        _manager.disconnect("events", websocket)


# ---------------------------------------------------------------------------
# Approvals WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/ws/approvals")
async def ws_approvals(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """
    Live approval queue stream.

    Broadcasts ``approval.created`` and ``approval.decided`` events so
    operators receive real-time notifications in the Security Center.
    """
    await websocket.accept()

    user_id = await _authenticate_ws(websocket, token)
    if not user_id:
        await websocket.send_text(_msg("error", {"detail": "Authentication required"}))
        await websocket.close(code=4001)
        return

    _manager.connect("approvals", websocket)
    logger.info("ws_approvals_connected", user_id=user_id)

    try:
        await websocket.send_text(_msg("connected", {"channel": "approvals", "user_id": user_id}))

        while True:
            await asyncio.sleep(10)
            await websocket.send_text(
                _msg(
                    "approval.heartbeat",
                    {"status": "ok"},
                )
            )
    except WebSocketDisconnect:
        logger.info("ws_approvals_disconnected", user_id=user_id)
    finally:
        _manager.disconnect("approvals", websocket)


# ---------------------------------------------------------------------------
# Broadcast utility (called by EventRouter handlers in production)
# ---------------------------------------------------------------------------


async def broadcast_event(channel: str, event_type: str, data: dict[str, Any]) -> None:
    """Broadcast an event to all WebSocket clients on *channel*."""
    await _manager.broadcast(channel, _msg(event_type, data))

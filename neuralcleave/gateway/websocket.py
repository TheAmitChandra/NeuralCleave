"""WebSocket connection manager and endpoint for the CortexFlow Gateway."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cortexflow_ai import __version__

logger = logging.getLogger(__name__)
router = APIRouter()


@dataclass
class Session:
    """A single active WebSocket client connection."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    websocket: WebSocket | None = None
    channel: str | None = None
    connected_at: float = field(default_factory=time.time)

    async def send(self, message: dict[str, Any]) -> None:
        """Send a JSON message to this session. Silently drops on failure."""
        if self.websocket is None:
            return
        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception as exc:
            logger.warning("send failed session=%s: %s", self.session_id, exc)


class WebSocketManager:
    """Manages all active WebSocket sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("WebSocketManager started")

    async def stop(self) -> None:
        self._running = False
        for session in list(self._sessions.values()):
            if session.websocket:
                try:
                    await session.websocket.close()
                except Exception:
                    pass
        self._sessions.clear()
        logger.info("WebSocketManager stopped, all sessions closed")

    def add(self, session: Session) -> None:
        self._sessions[session.session_id] = session
        logger.info("session.connected id=%s total=%d", session.session_id, len(self._sessions))

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        logger.info("session.disconnected id=%s total=%d", session_id, len(self._sessions))

    async def broadcast(self, message: dict[str, Any], channel: str | None = None) -> None:
        """Broadcast to all sessions, or only sessions on a specific channel."""
        targets = [
            s for s in self._sessions.values()
            if channel is None or s.channel == channel
        ]
        if targets:
            await asyncio.gather(*(s.send(message) for s in targets), return_exceptions=True)

    @property
    def session_count(self) -> int:
        return len(self._sessions)


# Module-level singleton shared by the FastAPI app
_manager = WebSocketManager()


def get_manager() -> WebSocketManager:
    return _manager


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Main WebSocket endpoint. Clients connect here for real-time messaging."""
    await websocket.accept()
    session = Session(websocket=websocket)
    manager = get_manager()
    manager.add(session)

    try:
        await session.send({
            "type": "hello",
            "session_id": session.session_id,
            "version": __version__,
            "timestamp": time.time(),
        })

        while True:
            raw = await websocket.receive_text()
            try:
                msg: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                await session.send({"type": "error", "message": "Invalid JSON"})
                continue

            await _handle_message(session, msg)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("ws error session=%s: %s", session.session_id, exc)
    finally:
        manager.remove(session.session_id)


async def _handle_message(session: Session, msg: dict[str, Any]) -> None:
    msg_type = msg.get("type", "")

    if msg_type == "ping":
        await session.send({"type": "pong", "timestamp": time.time()})

    elif msg_type == "subscribe":
        session.channel = msg.get("channel")
        await session.send({
            "type": "subscribed",
            "channel": session.channel,
            "timestamp": time.time(),
        })

    elif msg_type == "message":
        await _handle_chat_message(session, msg)

    else:
        await session.send({
            "type": "error",
            "message": f"Unknown message type: {msg_type!r}",
        })


async def _handle_chat_message(session: Session, msg: dict[str, Any]) -> None:
    """Dispatch a chat message to the AgentRuntime and stream the reply back.

    The runtime is resolved lazily via routes.get_runtime() (set by the gateway
    lifespan). If no runtime is registered yet, the client receives an error
    frame instead of a silent drop.

    Streams the reply as it's generated: zero or more "message_chunk" frames
    (each carrying one incremental "delta"), followed by exactly one
    "message_done" frame with the full assembled "text". A mid-stream
    failure (or the runtime being unavailable) sends the existing "error"
    frame shape instead — unchanged from the prior non-streaming protocol,
    so error handling on the client doesn't need to know which path failed.
    """
    from cortexflow_ai.gateway.routes import get_runtime

    text = (msg.get("text") or msg.get("payload") or "").strip()
    if not text:
        await session.send({"type": "error", "message": "Empty message"})
        return

    runtime = get_runtime()
    if runtime is None:
        await session.send({
            "type": "error",
            "message": "Agent runtime not available",
            "message_id": msg.get("id"),
        })
        return

    try:
        accumulated: list[str] = []
        async for chunk in runtime.process_inbound_text_stream(
            channel="websocket",
            sender_id=session.session_id,
            text=text,
        ):
            if chunk.error:
                await session.send({
                    "type": "error",
                    "message": chunk.error,
                    "message_id": msg.get("id"),
                })
                return
            if chunk.text:
                accumulated.append(chunk.text)
                await session.send({
                    "type": "message_chunk",
                    "message_id": msg.get("id"),
                    "delta": chunk.text,
                    "timestamp": time.time(),
                })
            if chunk.done:
                full_text = chunk.result.response if chunk.result else "".join(accumulated)
                await session.send({
                    "type": "message_done",
                    "message_id": msg.get("id"),
                    "text": full_text,
                    "timestamp": time.time(),
                })
    except Exception as exc:
        logger.error("ws chat error session=%s: %s", session.session_id, exc)
        await session.send({
            "type": "error",
            "message": "Failed to process message",
            "message_id": msg.get("id"),
        })

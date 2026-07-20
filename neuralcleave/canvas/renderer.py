"""CanvasRenderer — manages canvas state and broadcasts to WebSocket subscribers."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from neuralcleave.canvas.block import CanvasBlock

logger = logging.getLogger(__name__)

MAX_BLOCKS = 200


class CanvasRenderer:
    """Manages the live canvas state and pushes updates to all connected clients.

    Subscribers are WebSocket-like objects that expose ``send_text(str)``.
    A subscriber is automatically removed when its ``send_text`` raises.

    The internal block list is capped at ``MAX_BLOCKS`` (200). When the cap is
    reached the oldest blocks are dropped to make room for new ones.
    """

    def __init__(self) -> None:
        self._blocks: list[CanvasBlock] = []
        self._subscribers: list[Any] = []
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def add_block(self, block: CanvasBlock) -> None:
        """Append *block* to the canvas and broadcast to all subscribers."""
        async with self._lock:
            self._blocks.append(block)
            if len(self._blocks) > MAX_BLOCKS:
                self._blocks = self._blocks[-MAX_BLOCKS:]
        await self._broadcast({"type": "add", "block": block.to_dict()})
        logger.debug("canvas.add block_type=%s id=%s", block.block_type, block.id)

    async def clear(self) -> None:
        """Remove all blocks from the canvas and notify subscribers."""
        async with self._lock:
            self._blocks.clear()
        await self._broadcast({"type": "clear"})
        logger.debug("canvas.clear")

    def get_state(self) -> dict[str, Any]:
        """Return the current canvas state as a serialisable dict."""
        return {
            "blocks": [b.to_dict() for b in self._blocks],
            "count": len(self._blocks),
        }

    def block_count(self) -> int:
        """Number of blocks currently on the canvas."""
        return len(self._blocks)

    # ------------------------------------------------------------------
    # Subscriber management
    # ------------------------------------------------------------------

    async def subscribe(self, ws: Any) -> None:
        """Register *ws* as a subscriber and send the current state immediately."""
        self._subscribers.append(ws)
        try:
            payload = json.dumps(
                {
                    "type": "state",
                    "blocks": [b.to_dict() for b in self._blocks],
                }
            )
            await ws.send_text(payload)
        except Exception as exc:
            logger.debug("canvas.subscribe initial send failed: %s", exc)
            self._subscribers.remove(ws)

    def unsubscribe(self, ws: Any) -> None:
        """Remove *ws* from the subscriber list (no-op if not present)."""
        try:
            self._subscribers.remove(ws)
        except ValueError:
            pass

    def subscriber_count(self) -> int:
        """Number of active WebSocket subscribers."""
        return len(self._subscribers)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _broadcast(self, message: dict[str, Any]) -> None:
        """Send *message* to all subscribers; remove any that have closed."""
        if not self._subscribers:
            return
        text = json.dumps(message)
        dead: list[Any] = []
        for ws in list(self._subscribers):
            try:
                await ws.send_text(text)
            except Exception as exc:
                logger.debug("canvas.broadcast subscriber removed: %s", exc)
                dead.append(ws)
        for ws in dead:
            self.unsubscribe(ws)

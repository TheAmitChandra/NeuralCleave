"""App-scoped authentication for every WebSocket transport."""

from __future__ import annotations

from hmac import compare_digest

from starlette.datastructures import Headers, QueryParams
from starlette.types import ASGIApp, Receive, Scope, Send


class WebSocketAuthMiddleware:
    """Require the gateway key before dispatching any WebSocket handler.

    Browsers send ``token`` in the query string because they cannot set
    arbitrary handshake headers. Native clients may use X-API-Key instead.
    Route-level Origin checks apply independently.
    """

    def __init__(self, app: ASGIApp, api_key: str) -> None:
        self.app = app
        self.api_key = api_key.encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket" and self.api_key:
            headers = Headers(scope=scope)
            query = QueryParams(scope.get("query_string", b"").decode("ascii", errors="replace"))
            provided = headers.get("x-api-key") or query.get("token", "")
            if not compare_digest(provided.encode("utf-8"), self.api_key):
                await send({"type": "websocket.close", "code": 1008})
                return
        await self.app(scope, receive, send)

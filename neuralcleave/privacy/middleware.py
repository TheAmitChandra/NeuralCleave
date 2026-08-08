"""HTTPX transport wrapper that records every outbound request to the audit log.

Usage — wrap any ``httpx.AsyncClient`` you want to audit::

    import httpx
    from neuralcleave.privacy.middleware import AuditTransport
    from neuralcleave.privacy.audit import AUDIT_LOG

    async with httpx.AsyncClient(
        transport=AuditTransport(httpx.AsyncHTTPTransport(), AUDIT_LOG, session_id="abc"),
    ) as client:
        resp = await client.get("https://api.openai.com/v1/models")

The transport layer records the method and URL before forwarding the request
to the wrapped transport.  Errors in the wrapped transport are not swallowed —
they propagate normally after the entry has been recorded.
"""

from __future__ import annotations

import httpx

from neuralcleave.privacy.audit import PrivacyAuditLog


class AuditTransport(httpx.AsyncBaseTransport):
    """HTTPX async transport that logs each request to a PrivacyAuditLog.

    Args:
        transport:  The underlying transport to delegate actual I/O to.
        audit_log:  The ``PrivacyAuditLog`` instance to write entries to.
        session_id: Stable identifier for the current user session.
    """

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport,
        audit_log: PrivacyAuditLog,
        session_id: str,
    ) -> None:
        self._transport = transport
        self._audit_log = audit_log
        self._session_id = session_id

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        self._audit_log.record(
            session_id=self._session_id,
            method=request.method,
            url=str(request.url),
        )
        return await self._transport.handle_async_request(request)

    async def aclose(self) -> None:
        await self._transport.aclose()

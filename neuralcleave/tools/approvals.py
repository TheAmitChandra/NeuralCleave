"""Shell command approval queue.

When the ShellTool is configured with ``require_approval=True``, it queues
each command here and awaits an async gate that is opened by a user action
(``POST /api/v1/approvals/{id}/approve`` or ``/deny``).

Thread safety:
  The ``_entries`` dict and the ``asyncio.Event`` objects must only be
  touched from coroutines running in the same event loop — which is true
  for any code called from FastAPI route handlers and from ``ShellTool``
  when executed inside an async tool chain.

Typical flow::

    # Inside ShellTool.execute():
    req = APPROVAL_QUEUE.request("shell", command, {}, session_id="s1")
    approved = await req.wait()           # blocks until approved or denied
    if not approved:
        return ToolResult(error="Command denied by user.")
    # … proceed with subprocess …

    # Inside a route handler (from the web UI):
    APPROVAL_QUEUE.approve(request_id)   # unblocks the waiter
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApprovalRequest:
    """A single command waiting for user approval or denial."""

    id: str
    tool_name: str
    command: str
    arguments: dict[str, Any]
    session_id: str
    created_at: float = field(default_factory=time.time)
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _approved: bool = field(default=False, repr=False)

    # ------------------------------------------------------------------

    async def wait(self, timeout: float = 120.0) -> bool:
        """Block until the request is approved or denied.

        Args:
            timeout: Maximum seconds to wait. Denial is returned on timeout.

        Returns:
            ``True`` if approved, ``False`` if denied or timed out.
        """
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        return self._approved

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "command": self.command,
            "arguments": self.arguments,
            "session_id": self.session_id,
            "created_at": self.created_at,
        }


class ApprovalQueue:
    """In-process queue of pending shell command approvals.

    All methods are safe to call from multiple coroutines in the same
    event loop.
    """

    def __init__(self) -> None:
        self._entries: dict[str, ApprovalRequest] = {}

    # ------------------------------------------------------------------
    # Request lifecycle
    # ------------------------------------------------------------------

    def request(
        self,
        tool_name: str,
        command: str,
        arguments: dict[str, Any],
        session_id: str = "",
    ) -> ApprovalRequest:
        """Create and store a new approval request.

        Args:
            tool_name:  Name of the tool requesting approval (e.g. ``"shell"``).
            command:    Human-readable command string shown to the user.
            arguments:  Full argument dict for the tool call.
            session_id: Agent session that originated the request.

        Returns:
            The new :class:`ApprovalRequest` object.  Await its
            :meth:`ApprovalRequest.wait` to block until resolved.
        """
        req = ApprovalRequest(
            id=str(uuid.uuid4()),
            tool_name=tool_name,
            command=command,
            arguments=arguments,
            session_id=session_id,
        )
        self._entries[req.id] = req
        return req

    def approve(self, approval_id: str) -> bool:
        """Approve a pending request by ID.

        Returns:
            ``True`` if the request existed and was approved;
            ``False`` if not found (already resolved or unknown).
        """
        req = self._entries.pop(approval_id, None)
        if req is None:
            return False
        req._approved = True
        req._event.set()
        return True

    def deny(self, approval_id: str) -> bool:
        """Deny a pending request by ID.

        Returns:
            ``True`` if the request existed and was denied;
            ``False`` if not found.
        """
        req = self._entries.pop(approval_id, None)
        if req is None:
            return False
        req._approved = False
        req._event.set()
        return True

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def pending(self) -> list[dict[str, Any]]:
        """Return all pending (unresolved) requests as serialisable dicts."""
        return [r.to_dict() for r in self._entries.values()]

    def __len__(self) -> int:
        return len(self._entries)


# Module-level singleton used by ShellTool and gateway routes.
APPROVAL_QUEUE: ApprovalQueue = ApprovalQueue()

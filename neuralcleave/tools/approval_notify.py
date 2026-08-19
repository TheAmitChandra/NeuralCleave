"""Channel-forwarded approval — notify a user about a pending shell-command
approval in the channel that triggered it, and resolve their plain-text
"approve"/"deny" reply without a separate approvals UI visit.

P5 of the 2026-08-17 gap analysis: NeuralCleave already has 34 channel
adapters, so "approve via a reply in Slack/Telegram/Discord" is a natural,
low-effort extension of the existing :data:`neuralcleave.tools.approvals.APPROVAL_QUEUE`
rather than new infrastructure.

Usage::

    from neuralcleave.tools.approval_notify import notify_channel, try_resolve_approval_reply

    await notify_channel(adapter, target="12345", req=req)

    # On a later inbound message:
    reply = try_resolve_approval_reply(msg.text)
    if reply is not None:
        return reply  # short-circuits the normal agent pipeline
"""

from __future__ import annotations

import logging
from typing import Any

from neuralcleave.tools.approvals import ApprovalRequest

logger = logging.getLogger(__name__)

_ACTIONS = {"approve": True, "deny": False}


def format_approval_message(req: ApprovalRequest) -> str:
    """Human-readable notification text sent to the originating channel."""
    short_id = req.id[:8]
    return (
        f"Approval requested: {req.command}\n"
        f"Reply 'approve {short_id}' or 'deny {short_id}' to respond."
    )


async def notify_channel(adapter: Any, target: str, req: ApprovalRequest) -> bool:
    """Send an approval-request notification via *adapter* to *target*.

    Never raises — a failed notification should not block or crash the
    approval flow itself (the web approvals UI remains available as a
    fallback either way). Returns ``True`` if ``adapter.send()`` didn't
    raise, ``False`` otherwise.
    """
    try:
        await adapter.send(target, format_approval_message(req))
        return True
    except Exception as exc:
        logger.warning("approval_notify.send failed target=%s: %s", target, exc)
        return False


def try_resolve_approval_reply(text: str) -> str | None:
    """If *text* is an approval reply ('approve <id-prefix>' or
    'deny <id-prefix>'), resolve the matching pending request and return a
    confirmation string.

    Returns ``None`` when *text* doesn't match the reply pattern, or no
    pending request's id starts with the given prefix — callers should fall
    through to normal message handling in that case.
    """
    from neuralcleave.tools.approvals import APPROVAL_QUEUE

    parts = text.strip().lower().split(maxsplit=1)
    if len(parts) != 2 or parts[0] not in _ACTIONS:
        return None
    action, id_prefix = parts
    if not id_prefix:
        return None

    for pending in APPROVAL_QUEUE.pending():
        if pending["id"].startswith(id_prefix):
            approve = _ACTIONS[action]
            if approve:
                APPROVAL_QUEUE.approve(pending["id"])
                return f"Approved: {pending['command']}"
            APPROVAL_QUEUE.deny(pending["id"])
            return f"Denied: {pending['command']}"

    return None

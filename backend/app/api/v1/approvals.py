"""Approvals API — human-in-the-loop queue for high-risk agent actions.

Endpoints:
    GET  /api/v1/approvals/pending         — list PENDING requests
    GET  /api/v1/approvals/                — list all requests (all statuses)
    GET  /api/v1/approvals/{id}            — get one request
    POST /api/v1/approvals/{id}/approve    — operator approves
    POST /api/v1/approvals/{id}/reject     — operator rejects
    POST /api/v1/approvals/{id}/cancel     — originating agent cancels
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.approvals import ApprovalResponse, CancelRequest, RejectRequest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.governance.approvals import ApprovalWorkflow
from app.core.security.permission_engine import get_current_user
from app.db.models.user import User
from app.db.postgres import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/approvals")

# Application-level singleton — shared by API layer and agent runtime
_workflow = ApprovalWorkflow()





# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/pending", response_model=list[ApprovalResponse])
async def list_pending(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return all PENDING approval requests."""
    requests = await _workflow._store.list_pending()
    return [r.to_dict() for r in requests]


@router.get("/", response_model=list[ApprovalResponse])
async def list_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return all approval requests regardless of status."""
    requests = await _workflow._store.list_all()
    return [r.to_dict() for r in requests]


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return a single approval request by ID."""
    request = await _workflow._store.get(approval_id)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found",
        )
    return request.to_dict()


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
async def approve_request(
    approval_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Approve a PENDING approval request."""
    operator_id = str(current_user.id)
    try:
        await _workflow.approve(approval_id, operator_id=operator_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    request = await _workflow._store.get(approval_id)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found after decision",
        )
    logger.info("approval.approved_via_api", approval_id=approval_id, operator_id=operator_id)
    return request.to_dict()


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
async def reject_request(
    approval_id: str,
    body: RejectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reject a PENDING approval request with an optional reason."""
    operator_id = str(current_user.id)
    try:
        await _workflow.reject(
            approval_id,
            operator_id=operator_id,
            reason=body.reason,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    request = await _workflow._store.get(approval_id)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found after decision",
        )
    logger.info(
        "approval.rejected_via_api",
        approval_id=approval_id,
        operator_id=operator_id,
        reason=body.reason,
    )
    return request.to_dict()


@router.post("/{approval_id}/cancel", response_model=ApprovalResponse)
async def cancel_request(
    approval_id: str,
    body: CancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cancel a PENDING approval request (called by the originating agent)."""
    try:
        await _workflow.cancel(approval_id, actor_id=body.actor_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    request = await _workflow._store.get(approval_id)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found after cancel",
        )
    logger.info("approval.cancelled_via_api", approval_id=approval_id, actor_id=body.actor_id)
    return request.to_dict()

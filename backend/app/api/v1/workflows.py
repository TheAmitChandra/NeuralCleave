"""Workflows API — run, monitor, pause, resume, and rollback workflow executions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.schemas.workflows import (
    DagUpdateRequest,
    WorkflowActionResponse,
    WorkflowResponse,
    WorkflowRunRequest,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.permission_engine import get_current_user
from app.db.models.user import User
from app.db.models.workflow import Workflow
from app.db.postgres import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/workflows")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _workflow_to_dict(wf: Workflow) -> dict[str, Any]:
    return {
        "workflow_id": str(wf.id),
        "name": wf.name,
        "status": wf.status,
        "version": wf.version or 1,
        "owner_id": str(wf.owner_id),
        "agent_id": str(wf.agent_id) if wf.agent_id else None,
        "trigger_source": wf.trigger_source,
        "created_at": wf.created_at.isoformat() if wf.created_at else datetime.now(timezone.utc).isoformat(),
        "dag_definition": wf.dag_definition or {},
    }


async def _get_workflow_or_404(
    workflow_id: str, owner_id: uuid.UUID, db: AsyncSession
) -> Workflow:
    try:
        wid = uuid.UUID(workflow_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid workflow_id format")

    result = await db.execute(select(Workflow).where(Workflow.id == wid, Workflow.owner_id == owner_id))
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return wf


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def run_workflow(
    body: WorkflowRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Create and start a new workflow execution."""
    agent_id = None
    if body.agent_id:
        try:
            agent_id = uuid.UUID(body.agent_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid agent_id format")

    wf = Workflow(
        name=body.name,
        status="RUNNING",
        dag_definition=body.dag_definition,
        owner_id=current_user.id,
        agent_id=agent_id,
        trigger_source=body.trigger_source,
    )
    db.add(wf)
    await db.flush()
    logger.info("workflow_started", workflow_id=str(wf.id), name=wf.name, user_id=str(current_user.id))
    return _workflow_to_dict(wf)


@router.get("/", response_model=list[WorkflowResponse])
async def list_workflows(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List workflows for the authenticated user."""
    result = await db.execute(
        select(Workflow)
        .where(Workflow.owner_id == current_user.id)
        .order_by(Workflow.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_workflow_to_dict(w) for w in result.scalars().all()]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get a single workflow by ID."""
    wf = await _get_workflow_or_404(workflow_id, current_user.id, db)
    return _workflow_to_dict(wf)


@router.post("/{workflow_id}/pause", response_model=WorkflowActionResponse)
async def pause_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Pause a running workflow."""
    wf = await _get_workflow_or_404(workflow_id, current_user.id, db)
    if wf.status != "RUNNING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot pause a workflow in '{wf.status}' state")
    wf.status = "PAUSED"
    await db.flush()
    logger.info("workflow_paused", workflow_id=workflow_id)
    return {"workflow_id": workflow_id, "action": "pause", "status": "PAUSED", "message": "Workflow paused"}


@router.post("/{workflow_id}/resume", response_model=WorkflowActionResponse)
async def resume_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Resume a paused workflow."""
    wf = await _get_workflow_or_404(workflow_id, current_user.id, db)
    if wf.status != "PAUSED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot resume a workflow in '{wf.status}' state")
    wf.status = "RUNNING"
    await db.flush()
    logger.info("workflow_resumed", workflow_id=workflow_id)
    return {"workflow_id": workflow_id, "action": "resume", "status": "RUNNING", "message": "Workflow resumed"}


@router.post("/{workflow_id}/rollback", response_model=WorkflowActionResponse)
async def rollback_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Roll back a failed or paused workflow."""
    wf = await _get_workflow_or_404(workflow_id, current_user.id, db)
    if wf.status not in ("FAILED", "PAUSED", "RUNNING"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot rollback a workflow in '{wf.status}' state",
        )
    wf.status = "ROLLED_BACK"
    await db.flush()
    logger.info("workflow_rolled_back", workflow_id=workflow_id)
    return {"workflow_id": workflow_id, "action": "rollback", "status": "ROLLED_BACK", "message": "Workflow rolled back"}


@router.patch("/{workflow_id}/dag", response_model=WorkflowResponse)
async def update_dag(
    workflow_id: str,
    body: DagUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Persist the React Flow DAG definition for a workflow."""
    wf = await _get_workflow_or_404(workflow_id, current_user.id, db)
    wf.dag_definition = body.dag_definition
    await db.flush()
    logger.info("workflow_dag_updated", workflow_id=workflow_id)
    return _workflow_to_dict(wf)

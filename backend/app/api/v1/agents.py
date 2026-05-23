"""Agents API — CRUD + execution control for CortexFlow agents."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.permission_engine import get_current_user
from app.db.models.agent import Agent
from app.db.models.user import User
from app.db.postgres import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/agents")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    agent_type: str = Field(default="generic", max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentStatusPatch(BaseModel):
    status: str = Field(..., pattern=r"^(IDLE|PAUSED|TERMINATED)$")


class AgentExecuteRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=2048)
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    agent_type: str
    status: str
    owner_id: str
    created_at: str
    metadata: dict[str, Any]

    model_config = {"from_attributes": True}


class AgentExecuteResponse(BaseModel):
    agent_id: str
    task_id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agent_to_dict(agent: Agent) -> dict[str, Any]:
    return {
        "agent_id": str(agent.id),
        "name": agent.name,
        "agent_type": agent.agent_type,
        "status": agent.status,
        "owner_id": str(agent.owner_id),
        "created_at": agent.created_at.isoformat() if agent.created_at else datetime.now(timezone.utc).isoformat(),
        "metadata": agent.config or {},
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/create", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Create a new agent owned by the authenticated user."""
    agent = Agent(
        name=body.name,
        agent_type=body.agent_type,
        status="IDLE",
        owner_id=current_user.id,
        config=body.metadata,
    )
    db.add(agent)
    await db.flush()
    logger.info("agent_created", agent_id=str(agent.id), name=agent.name, user_id=str(current_user.id))
    return _agent_to_dict(agent)


@router.get("/", response_model=list[AgentResponse])
async def list_agents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List agents owned by the authenticated user."""
    result = await db.execute(
        select(Agent)
        .where(Agent.owner_id == current_user.id)
        .order_by(Agent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    agents = result.scalars().all()
    return [_agent_to_dict(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get a single agent by ID."""
    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid agent_id format")

    result = await db.execute(select(Agent).where(Agent.id == aid, Agent.owner_id == current_user.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return _agent_to_dict(agent)


@router.patch("/{agent_id}/status", response_model=AgentResponse)
async def update_agent_status(
    agent_id: str,
    body: AgentStatusPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update an agent's lifecycle status (IDLE | PAUSED | TERMINATED)."""
    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid agent_id format")

    result = await db.execute(select(Agent).where(Agent.id == aid, Agent.owner_id == current_user.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    agent.status = body.status
    await db.flush()
    logger.info("agent_status_updated", agent_id=agent_id, new_status=body.status)
    return _agent_to_dict(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Soft-delete an agent (sets status to TERMINATED)."""
    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid agent_id format")

    result = await db.execute(select(Agent).where(Agent.id == aid, Agent.owner_id == current_user.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    agent.status = "TERMINATED"
    await db.flush()
    logger.info("agent_deleted", agent_id=agent_id)


@router.post("/{agent_id}/execute", response_model=AgentExecuteResponse)
async def execute_agent_task(
    agent_id: str,
    body: AgentExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Submit a task for an agent to execute asynchronously."""
    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid agent_id format")

    result = await db.execute(select(Agent).where(Agent.id == aid, Agent.owner_id == current_user.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    if agent.status == "TERMINATED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot execute task on a terminated agent")

    task_id = str(uuid.uuid4())
    logger.info("agent_task_submitted", agent_id=agent_id, task_id=task_id, task=body.task[:100])

    return {
        "agent_id": agent_id,
        "task_id": task_id,
        "status": "QUEUED",
        "message": "Task submitted for execution",
    }

"""AuditLog model — immutable record of all system events."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # tool_execution | approval_granted | approval_rejected | permission_change
    # agent_created | workflow_started | security_violation | auth_event
    actor_id: Mapped[str | None] = mapped_column(String(255), index=True)  # user_id or agent_id
    actor_type: Mapped[str] = mapped_column(String(50), default="user")  # user | agent | system
    resource_type: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)  # success | failure | rejected
    details: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    trace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    risk_score: Mapped[str | None] = mapped_column(String(10))
    tenant_id: Mapped[str | None] = mapped_column(String(100), index=True)

    # Immutable — no updated_at
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

"""ToolCall model — every tool execution with full context."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tool_category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # browser | file | shell | api | db | ml | comms
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING"
    )  # PENDING | RUNNING | COMPLETED | FAILED | REJECTED | AWAITING_APPROVAL
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    isolation_level: Mapped[str] = mapped_column(
        String(50), default="low"
    )  # low | medium | high | critical
    input_params: Mapped[dict | None] = mapped_column(JSONB)
    output_data: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    trace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    requires_approval: Mapped[bool] = mapped_column(default=False)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    tenant_id: Mapped[str | None] = mapped_column(String(100), index=True)

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL")
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    task: Mapped["Task | None"] = relationship(back_populates="tool_calls")  # type: ignore[name-defined]  # noqa: F821

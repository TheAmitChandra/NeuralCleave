"""Task model — atomic task units with risk scores."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING", index=True
    )  # PENDING | RUNNING | VALIDATING | REFLECTING | COMPLETED | FAILED | RETRYING | ROLLED_BACK
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1 (low) to 10 (critical)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0–100
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    input_data: Mapped[dict | None] = mapped_column(JSONB)
    output_data: Mapped[dict | None] = mapped_column(JSONB)
    error_data: Mapped[dict | None] = mapped_column(JSONB)
    cognitive_stage: Mapped[str | None] = mapped_column(String(100))  # which pipeline stage
    tenant_id: Mapped[str | None] = mapped_column(String(100), index=True)

    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE")
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    workflow: Mapped["Workflow"] = relationship(back_populates="tasks")  # type: ignore[name-defined]  # noqa: F821
    agent: Mapped["Agent | None"] = relationship(back_populates="tasks")  # type: ignore[name-defined]  # noqa: F821
    tool_calls: Mapped[list["ToolCall"]] = relationship(back_populates="task", lazy="select")  # type: ignore[name-defined]  # noqa: F821

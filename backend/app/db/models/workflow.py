"""Workflow model — DAG definitions, versioned and immutable."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING", index=True
    )  # PENDING | RUNNING | PAUSED | COMPLETED | FAILED | ROLLED_BACK
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dag_definition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    checkpoint_data: Mapped[dict | None] = mapped_column(JSONB)
    trigger_source: Mapped[str | None] = mapped_column(
        String(100)
    )  # manual | cron | webhook | event
    tenant_id: Mapped[str | None] = mapped_column(String(100), index=True)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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
    tasks: Mapped[list["Task"]] = relationship(back_populates="workflow", lazy="select")  # type: ignore[name-defined]  # noqa: F821

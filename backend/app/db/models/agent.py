"""Agent model — agent registry and lifecycle state."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # planner | executor | validator | critic | memory | security | observer | router
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="IDLE", index=True
    )  # IDLE | PLANNING | EXECUTING | VALIDATING | REFLECTING | PAUSED | TERMINATED
    description: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    trust_score: Mapped[float] = mapped_column(Float, default=1.0)
    tenant_id: Mapped[str | None] = mapped_column(String(100), index=True)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    owner: Mapped["User"] = relationship(back_populates="agents")  # type: ignore[name-defined]  # noqa: F821
    tasks: Mapped[list["Task"]] = relationship(back_populates="agent", lazy="select")  # type: ignore[name-defined]  # noqa: F821

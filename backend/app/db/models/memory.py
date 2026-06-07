"""MemoryEntry model — episodic memory with Qdrant vector IDs."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # short_term | semantic | episodic | knowledge_graph
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    qdrant_vector_id: Mapped[str | None] = mapped_column(String(255), index=True)
    embedding_id: Mapped[str | None] = mapped_column(String(255), index=True)
    qdrant_collection: Mapped[str | None] = mapped_column(String(100))
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)  # 0.0–1.0
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict | None] = mapped_column(JSONB, name="metadata")
    tags: Mapped[list | None] = mapped_column(JSONB)
    tenant_id: Mapped[str | None] = mapped_column(String(100), index=True)

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

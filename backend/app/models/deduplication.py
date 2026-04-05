from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DedupCandidate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "dedup_candidates"

    record_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("health_records.id"), nullable=False
    )
    record_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("health_records.id"), nullable=False
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    match_reasons: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    llm_classification: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    auto_resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    source_upload_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploaded_files.id"), nullable=True
    )

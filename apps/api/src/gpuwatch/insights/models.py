"""Findings produced by the insights engine, and editable engine settings."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gpuwatch.core.db import Base, new_id


class Insight(Base):
    """One finding about one subject. At most one unresolved row per fingerprint
    (``kind:subject``): re-evaluation updates it, a cleared condition resolves it, and a
    recurrence later opens a new row."""

    __tablename__ = "insights"
    __table_args__ = (
        Index(
            "uq_insights_open_fingerprint",
            "fingerprint",
            unique=True,
            postgresql_where=text("status <> 'resolved'"),
        ),
        Index("ix_insights_status_seen", "status", "last_seen_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    host_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    gpu_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("gpus.id", ondelete="CASCADE"))
    endpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inference_endpoints.id", ondelete="CASCADE")
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Estimated cost of the problem over 30 days at the configured rate. An estimate, not a
    # promised saving; NULL when no rate is set or the finding has no direct cost.
    est_monthly_nusd: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class AppSetting(Base):
    """Settings edited in the dashboard (insight thresholds and the idle rule)."""

    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

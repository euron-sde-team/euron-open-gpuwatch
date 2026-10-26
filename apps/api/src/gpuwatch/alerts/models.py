"""Alert rules, the events they raise, notification channels and the delivery outbox."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gpuwatch.core.db import Base, TimestampMixin, new_id


class AlertRule(TimestampMixin, Base):
    """``threshold``: a GPU metric beyond a value for a duration. ``agent_offline``: a host
    stopped reporting. ``gpu_lost``: a GPU disappeared from a host that still reports."""

    __tablename__ = "alert_rules"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="threshold")
    metric: Mapped[str | None] = mapped_column(String(32))
    operator: Mapped[str | None] = mapped_column(String(4))
    threshold: Mapped[float | None] = mapped_column(Float)
    duration_s: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Scope: every GPU when all three are empty.
    scope_host_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE")
    )
    scope_gpu_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("gpus.id", ondelete="CASCADE")
    )
    scope_label: Mapped[str | None] = mapped_column(String(120))
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    channel_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    notify_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AlertEvent(Base):
    """One firing of one rule for one target. The partial unique index allows exactly one
    unresolved event per (rule, target), so concurrent evaluators cannot double fire."""

    __tablename__ = "alert_events"
    __table_args__ = (
        Index(
            "uq_alert_events_open",
            "rule_id",
            "target_key",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
        Index("ix_alert_events_started", "started_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False
    )
    target_key: Mapped[str] = mapped_column(String(64), nullable=False)
    host_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    gpu_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("gpus.id", ondelete="CASCADE"))
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Channel(TimestampMixin, Base):
    __tablename__ = "channels"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    emails: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    url: Mapped[str | None] = mapped_column(String(2000))
    # HMAC signing secret for webhooks, sealed (core/sealing.py).
    sealed_secret: Mapped[bytes | None] = mapped_column(LargeBinary)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class Notification(Base):
    """Transactional outbox: written in the same transaction as the event change, delivered
    by the worker with retries, so a crash never loses or duplicates a notification."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_pending",
            "next_attempt_at",
            postgresql_where=text("delivered_at IS NULL AND failed_at IS NULL"),
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("alert_events.id", ondelete="CASCADE"))
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    transition: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

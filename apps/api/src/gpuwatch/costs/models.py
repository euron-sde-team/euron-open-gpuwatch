"""Rates, workload rules, attributed usage and report exports.

Money is integer nano-dollars (``*_nusd``): exact sums, no float drift (docs/architecture/
adr/0002-integer-nano-dollars.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gpuwatch.core.db import Base, TimestampMixin, new_id


class GpuRate(TimestampMixin, Base):
    """What one GPU costs per hour. The most specific rate wins: a GPU, then its host, then
    its model name. There are no built-in prices: costs appear once a rate is set."""

    __tablename__ = "gpu_rates"
    __table_args__ = (
        CheckConstraint(
            "(scope = 'model' AND gpu_model IS NOT NULL AND host_id IS NULL AND gpu_id IS NULL)"
            " OR (scope = 'host' AND host_id IS NOT NULL AND gpu_id IS NULL)"
            " OR (scope = 'gpu' AND gpu_id IS NOT NULL)",
            name="ck_gpu_rates_scope",
        ),
        Index(
            "uq_gpu_rates_model",
            "gpu_model",
            unique=True,
            postgresql_where=text("scope = 'model'"),
        ),
        Index("uq_gpu_rates_host", "host_id", unique=True, postgresql_where=text("scope = 'host'")),
        Index("uq_gpu_rates_gpu", "gpu_id", unique=True, postgresql_where=text("scope = 'gpu'")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(8), nullable=False)
    gpu_model: Mapped[str | None] = mapped_column(String(120))
    host_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    gpu_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("gpus.id", ondelete="CASCADE"))
    nusd_per_hour: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorkloadRule(TimestampMixin, Base):
    """Maps GPU processes to a workload and a team. Rules are tried by ascending priority;
    the first whose every set condition matches wins. Unmatched processes are attributed
    to a workload named after the process."""

    __tablename__ = "workload_rules"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    workload: Mapped[str] = mapped_column(String(80), nullable=False)
    team: Mapped[str | None] = mapped_column(String(80))
    process_pattern: Mapped[str | None] = mapped_column(String(200))
    container_prefix: Mapped[str | None] = mapped_column(String(64))
    username: Mapped[str | None] = mapped_column(String(64))
    host_label: Mapped[str | None] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


IDLE_WORKLOAD = ""  # the unallocated bucket: GPU time with no process on it


class WorkloadUsage1h(Base):
    """GPU seconds per workload per hour. Every second of monitored time is in exactly one
    row: a workload's share, or the idle bucket (``workload = ''``), so per hour the rows
    add up to the GPU's monitored seconds."""

    __tablename__ = "workload_usage_1h"
    __table_args__ = (Index("ix_workload_usage_bucket", "bucket"),)
    gpu_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    workload: Mapped[str] = mapped_column(String(80), primary_key=True)
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    team: Mapped[str | None] = mapped_column(String(80))
    seconds: Mapped[float] = mapped_column(Float, nullable=False)
    # The part of ``seconds`` the workload held the GPU (processes, memory) without using
    # it: utilization under the idle threshold.
    idle_seconds: Mapped[float] = mapped_column(Float, nullable=False)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    group_by: Mapped[str] = mapped_column(String(16), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    object_key: Mapped[str] = mapped_column(String(200), nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    rows: Mapped[int] = mapped_column(Integer, nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

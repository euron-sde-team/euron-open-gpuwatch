"""Inference servers (vLLM, TGI) scraped by the agent, kept separate from GPU telemetry.

The agent turns each server's cumulative Prometheus counters into per-interval deltas, so a
row is the traffic of one interval. Histograms (time to first token, inter-token latency,
request latency) arrive as per-interval bucket counts keyed by upper bound, which sum
exactly across rows; percentiles are computed from the summed buckets.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gpuwatch.core.db import Base, TimestampMixin, new_id


class InferenceEndpoint(TimestampMixin, Base):
    __tablename__ = "inference_endpoints"
    __table_args__ = (UniqueConstraint("host_id", "name", name="uq_inference_endpoint_name"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    host_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200))
    # GPUs this server runs on (ids of rows in gpus): their cost is the server's cost.
    gpu_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class _InferenceMetrics:
    requests: Mapped[float | None] = mapped_column(Float)
    prompt_tokens: Mapped[float | None] = mapped_column(Float)
    generation_tokens: Mapped[float | None] = mapped_column(Float)
    # Histogram bucket counts: {"0.1": 3, "0.25": 9, ..., "+Inf": 12}. NULL: not exposed.
    ttft: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    itl: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    e2e: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class InferenceSample(_InferenceMetrics, Base):
    __tablename__ = "inference_samples"
    endpoint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    interval_s: Mapped[float] = mapped_column(Float, nullable=False)
    up: Mapped[bool] = mapped_column(Boolean, nullable=False)
    running: Mapped[float | None] = mapped_column(Float)
    waiting: Mapped[float | None] = mapped_column(Float)
    kv_cache_usage: Mapped[float | None] = mapped_column(Float)


class InferenceRollup1h(_InferenceMetrics, Base):
    __tablename__ = "inference_rollups_1h"
    endpoint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    seconds: Mapped[float] = mapped_column(Float, nullable=False)
    up_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    running_avg: Mapped[float | None] = mapped_column(Float)
    waiting_avg: Mapped[float | None] = mapped_column(Float)
    waiting_max: Mapped[float | None] = mapped_column(Float)
    kv_cache_avg: Mapped[float | None] = mapped_column(Float)
    kv_cache_max: Mapped[float | None] = mapped_column(Float)

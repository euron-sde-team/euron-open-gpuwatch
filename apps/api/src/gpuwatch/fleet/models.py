"""The fleet: enrolment tokens, the hosts agents run on, and the GPUs they report."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gpuwatch.core.db import Base, TimestampMixin, new_id


class EnrolmentToken(TimestampMixin, Base):
    """Exchanged by an agent for its own host token. Reusable (one token can enrol a fleet)
    until it expires, is revoked or reaches ``max_uses``. Only an HMAC is stored."""

    __tablename__ = "enrolment_tokens"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Labels every host enrolled with this token starts with (e.g. {"env": "prod"}).
    labels: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Hosts enrolled with a simulated token are demo hosts: badged in the UI, and allowed
    # to backfill history (real agents can only send recent samples).
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_uses: Mapped[int | None] = mapped_column(Integer)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Host(TimestampMixin, Base):
    __tablename__ = "hosts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    # Stable identity reported by the agent (/etc/machine-id or a generated id it keeps).
    machine_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    labels: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    token_prefix: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    enrolled_with: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("enrolment_tokens.id", ondelete="SET NULL")
    )
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    agent_version: Mapped[str | None] = mapped_column(String(32))
    collector: Mapped[str | None] = mapped_column(String(32))
    os: Mapped[str | None] = mapped_column(String(120))
    kernel: Mapped[str | None] = mapped_column(String(120))
    driver_version: Mapped[str | None] = mapped_column(String(64))
    cuda_version: Mapped[str | None] = mapped_column(String(32))
    # What the agent says about itself: ok, or degraded with problems (driver errors, NVML
    # not found, a collector that failed). Distinct from connectivity (last_seen_at).
    agent_status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    problems: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    interval_s: Mapped[float | None] = mapped_column(Float)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Gpu(Base):
    __tablename__ = "gpus"
    __table_args__ = (Index("ix_gpus_host", "host_id", "index"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    host_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False
    )
    # The driver's GPU UUID (GPU-xxxxxxxx-...), globally unique.
    uuid: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    memory_total_mib: Mapped[float | None] = mapped_column(Float)
    power_limit_w: Mapped[float | None] = mapped_column(Float)
    pci_bus_id: Mapped[str | None] = mapped_column(String(32))
    mig_mode: Mapped[bool | None] = mapped_column(Boolean)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Last time the host's agent reported this GPU. A GPU missing from the batches of a
    # host that is still reporting is "lost" (fell off the bus, driver reset).
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

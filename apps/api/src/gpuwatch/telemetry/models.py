"""Time series: raw samples (partitioned by day), rollups at 1 minute and 1 hour, and the
bookkeeping that keeps rollups exact when data arrives late.

Every metric column is nullable. NULL means the driver did not report it (unsupported on
this GPU, or a read error), which the API and the dashboard show as "Not available". It is
never stored as 0.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gpuwatch.core.db import Base

# NVML clocks event reasons (nvml.h, nvmlClocksEventReason*). The ones that slow a busy GPU
# down are grouped for findings: power, thermal, hardware.
THROTTLE_IDLE = 0x1
THROTTLE_APP_CLOCKS = 0x2
THROTTLE_SW_POWER_CAP = 0x4
THROTTLE_HW_SLOWDOWN = 0x8
THROTTLE_SYNC_BOOST = 0x10
THROTTLE_SW_THERMAL = 0x20
THROTTLE_HW_THERMAL = 0x40
THROTTLE_HW_POWER_BRAKE = 0x80
THROTTLE_DISPLAY_CLOCKS = 0x100
THROTTLE_POWER = THROTTLE_SW_POWER_CAP | THROTTLE_HW_POWER_BRAKE
THROTTLE_THERMAL = THROTTLE_SW_THERMAL | THROTTLE_HW_THERMAL
THROTTLE_HW = THROTTLE_HW_SLOWDOWN


class _Metrics:
    """Columns shared by raw samples."""

    util_gpu: Mapped[float | None] = mapped_column(Float)
    util_mem: Mapped[float | None] = mapped_column(Float)
    mem_used_mib: Mapped[float | None] = mapped_column(Float)
    mem_total_mib: Mapped[float | None] = mapped_column(Float)
    temp_c: Mapped[float | None] = mapped_column(Float)
    power_w: Mapped[float | None] = mapped_column(Float)
    power_limit_w: Mapped[float | None] = mapped_column(Float)
    fan_pct: Mapped[float | None] = mapped_column(Float)
    sm_clock_mhz: Mapped[float | None] = mapped_column(Float)
    mem_clock_mhz: Mapped[float | None] = mapped_column(Float)
    pstate: Mapped[int | None] = mapped_column(SmallInteger)
    throttle_reasons: Mapped[int | None] = mapped_column(BigInteger)
    pcie_rx_kbps: Mapped[float | None] = mapped_column(Float)
    pcie_tx_kbps: Mapped[float | None] = mapped_column(Float)
    ecc_uncorrected: Mapped[int | None] = mapped_column(BigInteger)
    xid: Mapped[int | None] = mapped_column(Integer)
    # Processes on the GPU at sample time; NULL when the driver does not list them.
    procs: Mapped[int | None] = mapped_column(SmallInteger)


class GpuSample(_Metrics, Base):
    """One reading of one GPU. Partitioned by day on ``ts``; old partitions are dropped
    whole once rolled up and past the raw retention."""

    __tablename__ = "gpu_samples"
    __table_args__ = (
        Index("ix_gpu_samples_host_ts", "host_id", "ts"),
        {"postgresql_partition_by": "RANGE (ts)"},
    )
    gpu_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Seconds this reading stands for (time since the agent's previous reading, capped).
    interval_s: Mapped[float] = mapped_column(Float, nullable=False)


class ProcessSample(Base):
    __tablename__ = "process_samples"
    __table_args__ = (
        Index("ix_process_samples_host_ts", "host_id", "ts"),
        {"postgresql_partition_by": "RANGE (ts)"},
    )
    gpu_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    pid: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    container_id: Mapped[str | None] = mapped_column(String(64))
    mem_used_mib: Mapped[float | None] = mapped_column(Float)
    # Share of the GPU's SM time this process used (nvmlDeviceGetProcessUtilization).
    sm_util: Mapped[float | None] = mapped_column(Float)


class _Rollup:
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    samples: Mapped[int] = mapped_column(Integer, nullable=False)
    seconds: Mapped[float] = mapped_column(Float, nullable=False)
    util_avg: Mapped[float | None] = mapped_column(Float)
    util_max: Mapped[float | None] = mapped_column(Float)
    util_mem_avg: Mapped[float | None] = mapped_column(Float)
    mem_used_avg: Mapped[float | None] = mapped_column(Float)
    mem_used_max: Mapped[float | None] = mapped_column(Float)
    mem_total: Mapped[float | None] = mapped_column(Float)
    temp_avg: Mapped[float | None] = mapped_column(Float)
    temp_max: Mapped[float | None] = mapped_column(Float)
    power_avg: Mapped[float | None] = mapped_column(Float)
    power_max: Mapped[float | None] = mapped_column(Float)
    energy_wh: Mapped[float | None] = mapped_column(Float)
    fan_avg: Mapped[float | None] = mapped_column(Float)
    sm_clock_avg: Mapped[float | None] = mapped_column(Float)
    # Seconds of busy time (utilization at or above 50%), and the part of it spent slowed
    # down for each throttle group. NULL when the driver reports no throttle reasons.
    busy_s: Mapped[float | None] = mapped_column(Float)
    throttle_power_s: Mapped[float | None] = mapped_column(Float)
    throttle_thermal_s: Mapped[float | None] = mapped_column(Float)
    throttle_hw_s: Mapped[float | None] = mapped_column(Float)
    procs_max: Mapped[int | None] = mapped_column(SmallInteger)
    ecc_max: Mapped[int | None] = mapped_column(BigInteger)
    xid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GpuRollup1m(_Rollup, Base):
    __tablename__ = "gpu_rollups_1m"
    __table_args__ = (Index("ix_gpu_rollups_1m_host_bucket", "host_id", "bucket"),)
    gpu_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)


class GpuRollup1h(_Rollup, Base):
    __tablename__ = "gpu_rollups_1h"
    __table_args__ = (Index("ix_gpu_rollups_1h_host_bucket", "host_id", "bucket"),)
    gpu_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)


class IngestBatch(Base):
    """Batch ids already accepted, so an agent replaying its spool never doubles data."""

    __tablename__ = "ingest_batches"
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class RollupDirty(Base):
    """A time range of one host whose rollups must be recomputed (samples arrived after
    the rollup job had closed those minutes: a spool replay, a demo backfill)."""

    __tablename__ = "rollup_dirty"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    to_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobState(Base):
    """Watermarks and last-run times of worker jobs (one row per job)."""

    __tablename__ = "job_state"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ran_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

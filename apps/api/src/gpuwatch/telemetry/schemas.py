"""Public contract of the telemetry domain (history and live)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from gpuwatch.core.schemas import ApiModel

Resolution = Literal["raw", "1m", "1h"]


class MetricPoint(ApiModel):
    ts: datetime
    util: float | None
    util_max: float | None
    util_mem: float | None
    mem_used_mib: float | None
    mem_used_max_mib: float | None
    mem_total_mib: float | None
    temp_c: float | None
    temp_max_c: float | None
    power_w: float | None
    power_max_w: float | None
    fan_pct: float | None
    sm_clock_mhz: float | None
    procs: int | None
    # Share of busy time slowed down, per group, 0 to 1 (raw points: 1 when the bit is set
    # during a busy sample, 0 otherwise). Null when the driver reports no throttle reasons.
    throttle_power: float | None
    throttle_thermal: float | None
    throttle_hw: float | None


class MetricSeries(ApiModel):
    gpu_id: uuid.UUID
    start: datetime
    end: datetime
    resolution: Resolution
    points: list[MetricPoint]
    # Which metrics this GPU reported at all in the window (others were never available).
    available: list[str]


class FleetPoint(ApiModel):
    ts: datetime
    util_avg: float | None
    mem_pct_avg: float | None
    power_w: float | None
    gpus: int


class FleetSeries(ApiModel):
    start: datetime
    end: datetime
    resolution: Resolution
    points: list[FleetPoint]


class ProcessOut(ApiModel):
    pid: int
    name: str
    username: str | None
    container_id: str | None
    mem_used_mib: float | None
    sm_util: float | None
    workload: str
    team: str | None


class WorkloadShare(ApiModel):
    workload: str
    label: str
    team: str | None
    gpu_hours: float
    idle_hours: float
    share: float = Field(description="Share of the GPU's monitored time, 0 to 1")


class GpuProcesses(ApiModel):
    gpu_id: uuid.UUID
    at: datetime | None = Field(description="Time of the newest process list")
    listed: bool = Field(description="False when the driver does not list processes")
    current: list[ProcessOut]
    window_hours: int
    workloads: list[WorkloadShare]

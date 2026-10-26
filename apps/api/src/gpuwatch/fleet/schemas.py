"""Public contract of the fleet domain."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints

from gpuwatch.core.schemas import ApiModel
from gpuwatch.ingest.schemas import Labels

HostStatus = Literal["online", "disconnected", "pending", "revoked"]
GpuStatus = Literal["ok", "lost", "offline", "retired"]


class EnrolmentTokenIn(ApiModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=120, strip_whitespace=True)]
    labels: Labels = Field(default_factory=dict, max_length=20)
    expires_in_days: Annotated[int, Field(ge=1, le=365)] | None = 30
    max_uses: Annotated[int, Field(ge=1, le=100_000)] | None = None


class EnrolmentTokenOut(ApiModel):
    id: uuid.UUID
    name: str
    display: str = Field(description="Safe identifier: gwe_<prefix>_****")
    labels: dict[str, Any]
    simulated: bool
    expires_at: datetime | None
    max_uses: int | None
    uses: int
    revoked_at: datetime | None
    created_at: datetime
    usable: bool


class EnrolmentTokenCreated(EnrolmentTokenOut):
    token: str = Field(description="Shown once. Give it to the agent as GPUWATCH_ENROLMENT_TOKEN")


class HostOut(ApiModel):
    id: uuid.UUID
    name: str
    hostname: str
    machine_id: str
    labels: dict[str, Any]
    status: HostStatus
    agent_status: Literal["ok", "degraded"]
    problems: list[dict[str, Any]]
    simulated: bool
    agent_version: str | None
    collector: str | None
    os: str | None
    kernel: str | None
    driver_version: str | None
    cuda_version: str | None
    interval_s: float | None
    gpu_count: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    created_at: datetime


class HostUpdate(ApiModel):
    display_name: (
        Annotated[str, StringConstraints(max_length=120, strip_whitespace=True)] | None
    ) = None
    labels: Labels | None = Field(default=None, max_length=20)


class GpuOut(ApiModel):
    id: uuid.UUID
    host_id: uuid.UUID
    host_name: str
    host_simulated: bool
    uuid: str
    index: int
    name: str
    memory_total_mib: float | None
    power_limit_w: float | None
    pci_bus_id: str | None
    mig_mode: bool | None
    status: GpuStatus
    first_seen_at: datetime
    last_seen_at: datetime | None
    retired_at: datetime | None
    nusd_per_hour: int | None = Field(description="The rate that applies, if any")
    rate_scope: Literal["gpu", "host", "model"] | None
    live: dict[str, Any] | None = Field(description="Newest sample, null when none is recent")


class GpuUpdate(ApiModel):
    retired: bool

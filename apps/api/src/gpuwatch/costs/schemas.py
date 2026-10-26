"""Public contract of the costs domain."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from gpuwatch.core.schemas import ApiModel

GroupBy = Literal["workload", "team", "host", "gpu", "model"]


class RateIn(ApiModel):
    scope: Literal["model", "host", "gpu"]
    gpu_model: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None
    host_id: uuid.UUID | None = None
    gpu_id: uuid.UUID | None = None
    usd_per_hour: Annotated[Decimal, Field(ge=0, le=100_000, decimal_places=6)]
    note: Annotated[str, StringConstraints(max_length=200)] | None = None

    @model_validator(mode="after")
    def _target(self) -> RateIn:
        target = {"model": self.gpu_model, "host": self.host_id, "gpu": self.gpu_id}[self.scope]
        if target is None:
            raise ValueError(f"a {self.scope} rate needs its {self.scope} set")
        return self


class RateUpdate(ApiModel):
    usd_per_hour: Annotated[Decimal, Field(ge=0, le=100_000, decimal_places=6)] | None = None
    note: Annotated[str, StringConstraints(max_length=200)] | None = None


class RateOut(ApiModel):
    id: uuid.UUID
    scope: str
    gpu_model: str | None
    host_id: uuid.UUID | None
    host_name: str | None
    gpu_id: uuid.UUID | None
    gpu_label: str | None
    nusd_per_hour: int
    usd_per_hour: float
    note: str | None
    gpus_covered: int
    updated_at: datetime


class WorkloadRuleIn(ApiModel):
    priority: Annotated[int, Field(ge=0, le=10_000)] = 100
    workload: Annotated[str, StringConstraints(min_length=1, max_length=80, strip_whitespace=True)]
    team: Annotated[str, StringConstraints(max_length=80, strip_whitespace=True)] | None = None
    process_pattern: Annotated[str, StringConstraints(max_length=200)] | None = None
    container_prefix: Annotated[str, StringConstraints(max_length=64)] | None = None
    username: Annotated[str, StringConstraints(max_length=64)] | None = None
    host_label: (
        Annotated[str, StringConstraints(max_length=120, pattern=r"^[A-Za-z0-9_.-]+=.{0,100}$")]
        | None
    ) = None
    enabled: bool = True

    @field_validator("process_pattern")
    @classmethod
    def _regex(cls, v: str | None) -> str | None:
        if v:
            try:
                re.compile(v)
            except re.error as exc:
                raise ValueError(f"not a valid regular expression: {exc}") from exc
        return v or None

    @model_validator(mode="after")
    def _some_condition(self) -> WorkloadRuleIn:
        if not any((self.process_pattern, self.container_prefix, self.username, self.host_label)):
            raise ValueError("a rule needs at least one condition to match on")
        return self


class WorkloadRuleOut(ApiModel):
    id: uuid.UUID
    priority: int
    workload: str
    team: str | None
    process_pattern: str | None
    container_prefix: str | None
    username: str | None
    host_label: str | None
    enabled: bool
    created_at: datetime


class CostRow(ApiModel):
    key: str
    label: str
    nusd: int
    # Part of nusd spent with the GPU held but not working (a workload's idle model), or
    # for the idle bucket, all of it.
    idle_nusd: int
    gpu_hours: float
    share: float = Field(description="Share of the total cost, 0 to 1")


class CostSummary(ApiModel):
    start: datetime
    end: datetime
    group_by: GroupBy
    total_nusd: int
    idle_nusd: int = Field(description="Cost of GPU time with nothing running")
    held_idle_nusd: int = Field(description="Cost of GPU time held by a workload but unused")
    gpu_hours: float
    unpriced_gpu_hours: float = Field(description="Monitored hours of GPUs that have no rate")
    rows: list[CostRow]


class CostSeriesPoint(ApiModel):
    bucket: datetime
    values: dict[str, int]


class CostSeries(ApiModel):
    start: datetime
    end: datetime
    group_by: GroupBy
    interval: Literal["hour", "day"]
    keys: list[str]
    labels: dict[str, str]
    points: list[CostSeriesPoint]


class ReportIn(ApiModel):
    group_by: GroupBy
    start: datetime
    end: datetime
    note: Annotated[str, StringConstraints(max_length=500)] | None = None


class ReportOut(ApiModel):
    id: uuid.UUID
    group_by: str
    params: dict[str, str]
    filename: str
    rows: int
    bytes: int
    total_nusd: int
    note: str | None
    created_at: datetime

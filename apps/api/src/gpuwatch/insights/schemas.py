"""Public contract of the insights domain."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from gpuwatch.core.schemas import ApiModel

InsightStatus = Literal["open", "acknowledged", "dismissed", "resolved"]


class InsightOut(ApiModel):
    id: uuid.UUID
    kind: str
    severity: Literal["info", "warning", "critical"]
    title: str
    summary: str
    recommendation: str
    evidence: dict[str, Any]
    window_start: datetime
    window_end: datetime
    est_monthly_nusd: int | None
    status: InsightStatus
    host_id: uuid.UUID | None
    host_name: str | None
    gpu_id: uuid.UUID | None
    gpu_label: str | None
    endpoint_id: uuid.UUID | None
    endpoint_name: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None


class InsightAction(ApiModel):
    action: Literal["acknowledge", "dismiss", "reopen"]


class Explanation(ApiModel):
    gpu_id: uuid.UUID
    window_days: int
    headline: str
    sentences: list[str]
    cost_nusd: int | None
    idle_nusd: int | None
    held_idle_nusd: int | None
    findings: list[InsightOut]

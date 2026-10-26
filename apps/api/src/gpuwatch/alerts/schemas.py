"""Public contract of the alerts domain."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from gpuwatch.core.schemas import ApiModel, Email

Metric = Literal[
    "util_gpu", "util_mem", "mem_used_pct", "temp_c", "power_w", "power_pct", "fan_pct"
]
Severity = Literal["info", "warning", "critical"]
RuleKind = Literal["threshold", "agent_offline", "gpu_lost"]

METRIC_LABELS: dict[str, tuple[str, str]] = {
    "util_gpu": ("GPU utilization", "%"),
    "util_mem": ("Memory bandwidth utilization", "%"),
    "mem_used_pct": ("Memory used", "%"),
    "temp_c": ("Temperature", "°C"),
    "power_w": ("Power draw", "W"),
    "power_pct": ("Power draw of limit", "%"),
    "fan_pct": ("Fan speed", "%"),
}


class RuleIn(ApiModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=120, strip_whitespace=True)]
    kind: RuleKind = "threshold"
    metric: Metric | None = None
    operator: Literal["gt", "lt"] | None = None
    threshold: float | None = None
    duration_s: Annotated[int, Field(ge=0, le=86_400)] = 60
    scope_host_id: uuid.UUID | None = None
    scope_gpu_id: uuid.UUID | None = None
    scope_label: (
        Annotated[str, StringConstraints(max_length=120, pattern=r"^[A-Za-z0-9_.-]+=.{0,100}$")]
        | None
    ) = None
    severity: Severity = "warning"
    channel_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    notify_resolved: bool = True
    enabled: bool = True

    @model_validator(mode="after")
    def _threshold(self) -> RuleIn:
        if self.kind == "threshold" and (
            self.metric is None or self.operator is None or self.threshold is None
        ):
            raise ValueError("a threshold rule needs a metric, an operator and a threshold")
        if self.kind != "threshold":
            self.metric = self.operator = None
            self.threshold = None
        return self


class RuleOut(ApiModel):
    id: uuid.UUID
    name: str
    kind: RuleKind
    metric: str | None
    operator: str | None
    threshold: float | None
    duration_s: int
    scope_host_id: uuid.UUID | None
    scope_gpu_id: uuid.UUID | None
    scope_label: str | None
    severity: Severity
    channel_ids: list[uuid.UUID]
    notify_resolved: bool
    enabled: bool
    description: str
    firing: int
    created_at: datetime


class EventOut(ApiModel):
    id: int
    rule_id: uuid.UUID
    rule_name: str
    kind: RuleKind
    severity: Severity
    message: str
    value: float | None
    host_id: uuid.UUID | None
    host_name: str | None
    gpu_id: uuid.UUID | None
    gpu_label: str | None
    started_at: datetime
    resolved_at: datetime | None
    notifications: int
    notifications_failed: int


class ChannelIn(ApiModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=120, strip_whitespace=True)]
    kind: Literal["email", "webhook"]
    emails: list[Email] = Field(default_factory=list, max_length=20)
    url: Annotated[str, StringConstraints(max_length=2000)] | None = None
    # Webhooks only. Omit on update to keep the current secret; empty to clear it.
    secret: Annotated[str, StringConstraints(max_length=200)] | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def _target(self) -> ChannelIn:
        if self.kind == "email" and not self.emails:
            raise ValueError("an email channel needs at least one address")
        if self.kind == "webhook" and not self.url:
            raise ValueError("a webhook channel needs a URL")
        return self


class ChannelOut(ApiModel):
    id: uuid.UUID
    name: str
    kind: Literal["email", "webhook"]
    emails: list[str]
    url: str | None
    signed: bool = Field(description="Webhook deliveries carry an HMAC signature")
    enabled: bool
    last_delivery_at: datetime | None
    last_error: str | None
    created_at: datetime


class NotificationOut(ApiModel):
    id: int
    event_id: int | None
    channel_id: uuid.UUID
    channel_name: str
    transition: str
    attempts: int
    delivered_at: datetime | None
    failed_at: datetime | None
    next_attempt_at: datetime
    last_error: str | None
    created_at: datetime

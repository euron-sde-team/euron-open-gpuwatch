"""Public contract of the inference module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from gpuwatch.core.schemas import ApiModel


class InferenceStats(ApiModel):
    seconds: float
    requests: float | None
    requests_per_s: float | None
    prompt_tokens: float | None
    generation_tokens: float | None
    generation_tokens_per_s: float | None
    ttft_p50_s: float | None = Field(description="Null when the server exposes no TTFT histogram")
    ttft_p95_s: float | None
    itl_p50_s: float | None
    itl_p95_s: float | None
    e2e_p50_s: float | None
    e2e_p95_s: float | None
    running_avg: float | None
    waiting_avg: float | None
    kv_cache_avg: float | None
    gpu_util_avg: float | None
    gpu_cost_nusd: int | None = Field(description="Cost of the bound GPUs over the window")
    nusd_per_million_tokens: int | None
    nusd_per_request: int | None


class EndpointOut(ApiModel):
    id: uuid.UUID
    host_id: uuid.UUID
    host_name: str
    name: str
    kind: str
    url: str
    model: str | None
    gpu_ids: list[uuid.UUID]
    gpu_labels: list[str]
    up: bool
    last_seen_at: datetime | None
    stats_24h: InferenceStats


class InferencePoint(ApiModel):
    ts: datetime
    requests_per_s: float | None
    prompt_tokens_per_s: float | None
    generation_tokens_per_s: float | None
    ttft_p50_s: float | None
    ttft_p95_s: float | None
    itl_p50_s: float | None
    e2e_p95_s: float | None
    running: float | None
    waiting: float | None
    kv_cache: float | None


class InferenceSeries(ApiModel):
    endpoint_id: uuid.UUID
    start: datetime
    end: datetime
    bucket_s: int
    summary: InferenceStats
    points: list[InferencePoint]

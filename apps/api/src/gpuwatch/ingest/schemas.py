"""The agent wire contract (``POST /ingest/v1/*``).

Agents are untrusted input: every field is bounded, and every metric is optional. A metric
the driver did not report is sent as ``null`` and stored as NULL, never as 0. A reading
outside what any GPU can report (a driver sentinel, a corrupt counter) is stored as NULL
too, instead of refusing the batch: one odd fan reading must not cost every other metric,
and an absurd value must never reach the rollup arithmetic.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BeforeValidator, Field, StringConstraints

from gpuwatch.core.schemas import ApiModel

Short = Annotated[str, StringConstraints(max_length=120, strip_whitespace=True)]
Name = Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]


def _within(lo: float, hi: float) -> Callable[[Any], Any]:
    def check(value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return value  # None stays None; anything else fails the type check
        return value if math.isfinite(value) and lo <= value <= hi else None

    return check


# A float or integer metric; outside its range or not finite, it becomes NULL ("Not available").
Pct = Annotated[float | None, BeforeValidator(_within(0, 100))]
MiB = Annotated[float | None, BeforeValidator(_within(0, 2**24))]  # 16 TiB
Watts = Annotated[float | None, BeforeValidator(_within(0, 5_000))]
MHz = Annotated[float | None, BeforeValidator(_within(0, 20_000))]
Kbps = Annotated[float | None, BeforeValidator(_within(0, 1e9))]  # 1 TB/s
Celsius = Annotated[float | None, BeforeValidator(_within(-50, 200))]
# NVML documents fan speeds above 100% on some boards.
FanPct = Annotated[float | None, BeforeValidator(_within(0, 400))]
Share = Annotated[float | None, BeforeValidator(_within(0, 1))]
Amount = Annotated[float | None, BeforeValidator(_within(0, 1e12))]  # inference deltas, gauges
SmallCount = Annotated[int | None, BeforeValidator(_within(0, 10_000))]
Flags = Annotated[int | None, BeforeValidator(_within(0, 2**62 - 1))]
Xid = Annotated[int | None, BeforeValidator(_within(0, 2**31 - 1))]
PState = Annotated[int | None, BeforeValidator(_within(0, 32))]
Datetime = AwareDatetime


def _bucket_key(key: str) -> str:
    if key != "+Inf":
        float(key)  # raises ValueError, which pydantic reports as a validation error
    return key


BucketKey = Annotated[str, StringConstraints(max_length=24), BeforeValidator(_bucket_key)]
Labels = dict[
    Annotated[str, StringConstraints(min_length=1, max_length=63, pattern=r"^[A-Za-z0-9_.-]+$")],
    Annotated[str, StringConstraints(max_length=120)],
]


class Problem(ApiModel):
    code: Annotated[str, StringConstraints(max_length=64)]
    message: Annotated[str, StringConstraints(max_length=500)]


class AgentInfo(ApiModel):
    version: Short
    collector: Literal["nvml", "dcgm", "simulated"]
    hostname: Name
    os: Short | None = None
    kernel: Short | None = None
    driver_version: Short | None = None
    cuda_version: Short | None = None
    interval_s: Annotated[float, Field(gt=0, le=3600)]
    # ok, or degraded: the agent runs but a collector failed (problems say why).
    status: Literal["ok", "degraded"] = "ok"
    problems: list[Problem] = Field(default_factory=list, max_length=20)


class GpuInfo(ApiModel):
    uuid: Annotated[str, StringConstraints(min_length=1, max_length=96)]
    index: Annotated[int, Field(ge=0, le=1024)]
    name: Name
    memory_total_mib: MiB = None
    power_limit_w: Watts = None
    pci_bus_id: Annotated[str, StringConstraints(max_length=32)] | None = None
    mig_mode: bool | None = None


class GpuSampleIn(ApiModel):
    gpu_uuid: Annotated[str, StringConstraints(min_length=1, max_length=96)]
    ts: Datetime
    interval_s: Annotated[float, Field(gt=0, le=3600)]
    util_gpu: Pct = None
    util_mem: Pct = None
    mem_used_mib: MiB = None
    mem_total_mib: MiB = None
    temp_c: Celsius = None
    power_w: Watts = None
    power_limit_w: Watts = None
    fan_pct: FanPct = None
    sm_clock_mhz: MHz = None
    mem_clock_mhz: MHz = None
    pstate: PState = None
    throttle_reasons: Flags = None
    pcie_rx_kbps: Kbps = None
    pcie_tx_kbps: Kbps = None
    ecc_uncorrected: Flags = None
    xid: Xid = None
    procs: SmallCount = None


class ProcessIn(ApiModel):
    gpu_uuid: Annotated[str, StringConstraints(min_length=1, max_length=96)]
    ts: Datetime
    pid: Annotated[int, Field(ge=0, lt=2**31)]
    name: Name
    username: Annotated[str, StringConstraints(max_length=64)] | None = None
    container_id: Annotated[str, StringConstraints(max_length=64)] | None = None
    mem_used_mib: MiB = None
    sm_util: Pct = None


Buckets = dict[BucketKey, Annotated[float, Field(ge=0, le=1e12)]]


class InferenceIn(ApiModel):
    endpoint: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    kind: Literal["vllm", "tgi"]
    url: Annotated[str, StringConstraints(max_length=500)]
    model: Annotated[str, StringConstraints(max_length=200)] | None = None
    gpu_uuids: list[Annotated[str, StringConstraints(max_length=96)]] = Field(
        default_factory=list, max_length=64
    )
    ts: Datetime
    interval_s: Annotated[float, Field(gt=0, le=3600)]
    up: bool
    # Per-interval deltas of the server's counters; null when the server does not expose
    # the metric (TGI has no time-to-first-token histogram, for instance).
    requests: Amount = None
    prompt_tokens: Amount = None
    generation_tokens: Amount = None
    running: Amount = None
    waiting: Amount = None
    kv_cache_usage: Share = None
    ttft: Buckets | None = Field(default=None, max_length=64)
    itl: Buckets | None = Field(default=None, max_length=64)
    e2e: Buckets | None = Field(default=None, max_length=64)


class Batch(ApiModel):
    # Generated by the agent; resending the same batch (spool replay) is a no-op.
    batch_id: uuid.UUID
    agent: AgentInfo
    gpus: list[GpuInfo] = Field(default_factory=list, max_length=256)
    samples: list[GpuSampleIn] = Field(default_factory=list)
    processes: list[ProcessIn] = Field(default_factory=list)
    inference: list[InferenceIn] = Field(default_factory=list, max_length=2_000)


class BatchAccepted(ApiModel):
    accepted: bool
    duplicate: bool
    samples: int
    processes: int
    inference: int
    # Rows refused: outside the accepted time window, or for a GPU the batch did not declare.
    dropped: int
    # Seconds the agent should wait before its next batch (the server may slow agents).
    next_in_s: float


class EnrolIn(ApiModel):
    token: Annotated[str, StringConstraints(min_length=10, max_length=200)]
    machine_id: Annotated[
        str, StringConstraints(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    ]
    hostname: Name
    labels: Labels = Field(default_factory=dict, max_length=20)


class Enrolled(ApiModel):
    host_id: uuid.UUID
    host_token: str = Field(description="gwh_...: send as 'Authorization: Bearer' on batches")
    simulated: bool

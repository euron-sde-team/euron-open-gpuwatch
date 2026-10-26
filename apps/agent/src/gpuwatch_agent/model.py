"""What a collector reads in one interval. Every metric is optional: ``None`` means the
driver did not report it, and it is sent as ``null`` (never 0)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class GpuInfo:
    uuid: str
    index: int
    name: str
    memory_total_mib: float | None = None
    power_limit_w: float | None = None
    pci_bus_id: str | None = None
    mig_mode: bool | None = None


@dataclass
class GpuSample:
    gpu_uuid: str
    ts: datetime
    interval_s: float
    util_gpu: float | None = None
    util_mem: float | None = None
    mem_used_mib: float | None = None
    mem_total_mib: float | None = None
    temp_c: float | None = None
    power_w: float | None = None
    power_limit_w: float | None = None
    fan_pct: float | None = None
    sm_clock_mhz: float | None = None
    mem_clock_mhz: float | None = None
    pstate: int | None = None
    throttle_reasons: int | None = None
    pcie_rx_kbps: float | None = None
    pcie_tx_kbps: float | None = None
    ecc_uncorrected: int | None = None
    xid: int | None = None
    procs: int | None = None


@dataclass
class ProcessSample:
    gpu_uuid: str
    ts: datetime
    pid: int
    name: str
    username: str | None = None
    container_id: str | None = None
    mem_used_mib: float | None = None
    sm_util: float | None = None


@dataclass
class Problem:
    code: str
    message: str


@dataclass
class Reading:
    gpus: list[GpuInfo] = field(default_factory=list)
    samples: list[GpuSample] = field(default_factory=list)
    processes: list[ProcessSample] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    driver_version: str | None = None
    cuda_version: str | None = None


def to_json(obj: Any) -> Any:
    """Dataclasses to JSON-ready dicts (datetimes as ISO 8601, NaN and infinity as null).

    JSON has no NaN: a server gauge reporting one would otherwise make the whole batch
    invalid, so a reading that is not a number is sent as "not available".
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, list):
        return [to_json(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_json(v) for k, v in obj.items()}
    if hasattr(obj, "__dataclass_fields__"):
        return to_json(asdict(obj))
    return obj

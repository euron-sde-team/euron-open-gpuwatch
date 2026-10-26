"""The insights engine: turns minute rollups into findings with evidence.

Pure functions over plain data (no database), so every rule is unit tested with exact
inputs. Each finding says what was observed, over which window, what it cost at the
configured rate (when there is one), and what to do. Costs are estimates from the user's
own rates; GPUWatch never claims a saving and never acts on a machine.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from gpuwatch.costs.rates import seconds_cost
from gpuwatch.insights.settings import InsightSettings

MINUTE = timedelta(minutes=1)
HOURS_PER_MONTH = 730


@dataclass(frozen=True, slots=True)
class Minute:
    bucket: datetime
    seconds: float
    util_avg: float | None
    util_max: float | None
    mem_used_max: float | None
    mem_total: float | None
    procs_max: int | None
    busy_s: float | None
    throttle_power_s: float | None
    throttle_thermal_s: float | None
    throttle_hw_s: float | None
    ecc_max: int | None
    xid_count: int


@dataclass(frozen=True, slots=True)
class GpuContext:
    id: uuid.UUID
    host_id: uuid.UUID
    name: str
    label: str
    memory_total_mib: float | None
    nusd_per_hour: int | None
    # Workloads that held this GPU while idle in the window, most idle time first.
    idle_holders: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """A GPU model in the fleet with a model-level rate: a candidate to move work to."""

    model: str
    memory_total_mib: float
    nusd_per_hour: int


@dataclass
class Finding:
    kind: str
    subject: str
    severity: str
    title: str
    summary: str
    recommendation: str
    window_start: datetime
    window_end: datetime
    evidence: dict[str, Any] = field(default_factory=dict)
    est_monthly_nusd: int | None = None
    host_id: uuid.UUID | None = None
    gpu_id: uuid.UUID | None = None
    endpoint_id: uuid.UUID | None = None

    @property
    def fingerprint(self) -> str:
        return f"{self.kind}:{self.subject}"


def usd(nusd: int) -> str:
    value = nusd / 1e9
    return f"${value:,.2f}" if value >= 0.01 or value == 0 else f"${value:.4f}"


def hours(seconds: float) -> str:
    h = seconds / 3600
    return f"{h:.1f} h" if h < 100 else f"{h:,.0f} h"


def gib(mib: float) -> str:
    return f"{mib / 1024:.1f} GiB"


def _monthly(cost: int, monitored_s: float) -> int | None:
    """Scale a window's cost to 30 days, once there is at least a day of data."""
    if monitored_s < 86400:
        return None
    return round(cost * 30 * 86400 / monitored_s)


# ── idle ─────────────────────────────────────────────────────────────────────


def _held(m: Minute, cfg: InsightSettings) -> bool:
    if m.procs_max:
        return True
    if m.mem_used_max is not None and m.mem_total:
        return 100 * m.mem_used_max / m.mem_total >= cfg.held_mem_pct
    return False


def _idle(m: Minute, cfg: InsightSettings) -> bool:
    return m.util_avg is not None and m.util_avg < cfg.idle_util_pct


def idle_runs(
    minutes: Sequence[Minute], predicate: Any, min_minutes: int
) -> list[tuple[datetime, datetime, float]]:
    """Runs of consecutive minutes matching ``predicate`` lasting at least ``min_minutes``:
    (start, end, seconds). A missing minute (no data) ends a run."""
    runs: list[tuple[datetime, datetime, float]] = []
    start: datetime | None = None
    prev: datetime | None = None
    count = 0
    secs = 0.0
    for m in minutes:
        contiguous = prev is not None and m.bucket - prev == MINUTE
        if predicate(m) and (start is None or contiguous):
            if start is None:
                start, count, secs = m.bucket, 0, 0.0
            count += 1
            secs += m.seconds
        else:
            if start is not None and prev is not None and count >= min_minutes:
                runs.append((start, prev + MINUTE, secs))
            start = None
            if predicate(m):
                start, count, secs = m.bucket, 1, m.seconds
        prev = m.bucket
    if start is not None and prev is not None and count >= min_minutes:
        runs.append((start, prev + MINUTE, secs))
    return runs


def idle_findings(
    gpu: GpuContext,
    minutes: Sequence[Minute],
    cfg: InsightSettings,
    window: tuple[datetime, datetime],
) -> list[Finding]:
    monitored = sum(m.seconds for m in minutes)
    out = []
    for kind, held in (("idle_loaded", True), ("idle_empty", False)):
        runs = idle_runs(
            minutes, lambda m, h=held: _idle(m, cfg) and _held(m, cfg) == h, cfg.idle_min_minutes
        )
        idle_s = sum(r[2] for r in runs)
        share = idle_s / monitored if monitored else 0.0
        if not runs or share < cfg.idle_min_share:
            continue
        cost = seconds_cost(idle_s, gpu.nusd_per_hour) if gpu.nusd_per_hour is not None else None
        longest = max(runs, key=lambda r: r[1] - r[0])
        evidence: dict[str, Any] = {
            "idle_seconds": round(idle_s, 1),
            "idle_hours": round(idle_s / 3600, 3),
            "monitored_hours": round(monitored / 3600, 3),
            "share": round(share, 4),
            "runs": len(runs),
            "longest": {"start": longest[0].isoformat(), "end": longest[1].isoformat()},
            "periods": [
                {"start": s.isoformat(), "end": e.isoformat(), "hours": round(sec / 3600, 3)}
                for s, e, sec in sorted(runs, key=lambda r: r[1] - r[0], reverse=True)[:10]
            ],
            "idle_util_pct": cfg.idle_util_pct,
            "min_minutes": cfg.idle_min_minutes,
            "nusd_per_hour": gpu.nusd_per_hour,
            "cost_nusd": cost,
        }
        price = (
            f" At {usd(gpu.nusd_per_hour)}/h that is {usd(cost)}."
            if cost is not None and gpu.nusd_per_hour is not None
            else " Set a rate in Costs to see what it cost."
        )
        if held:
            holders = ", ".join(gpu.idle_holders[:3]) if gpu.idle_holders else "a process"
            evidence["holders"] = list(gpu.idle_holders[:5])
            title = f"Model loaded but idle for {hours(idle_s)}"
            summary = (
                f"{gpu.label} ({gpu.name}) was held by {holders} with utilization under "
                f"{cfg.idle_util_pct:g}% for {hours(idle_s)} over the window "
                f"({share:.0%} of monitored time).{price}"
            )
            recommendation = (
                "Unload the model or stop the server when it has no traffic (scale to zero "
                "after a quiet period), or consolidate it onto a GPU that is already busy. "
                "GPUWatch never stops processes itself."
            )
        else:
            title = f"Nothing running for {hours(idle_s)}"
            summary = (
                f"{gpu.label} ({gpu.name}) had no processes and under "
                f"{cfg.idle_util_pct:g}% utilization for {hours(idle_s)} "
                f"({share:.0%} of monitored time).{price}"
            )
            recommendation = (
                "Release or stop the machine while it is not needed, or schedule work onto "
                "it. On a cloud instance, an idle GPU costs the same as a busy one."
            )
        out.append(
            Finding(
                kind=kind,
                subject=str(gpu.id),
                severity="warning" if share >= 0.25 else "info",
                title=title,
                summary=summary,
                recommendation=recommendation,
                window_start=window[0],
                window_end=window[1],
                evidence=evidence,
                est_monthly_nusd=_monthly(cost, monitored) if cost is not None else None,
                host_id=gpu.host_id,
                gpu_id=gpu.id,
            )
        )
    return out


# ── underused and oversized ──────────────────────────────────────────────────


def underused_finding(
    gpu: GpuContext,
    minutes: Sequence[Minute],
    cfg: InsightSettings,
    window: tuple[datetime, datetime],
) -> Finding | None:
    working = [
        m
        for m in minutes
        if m.procs_max and m.util_avg is not None and m.util_avg >= cfg.idle_util_pct
    ]
    busy_s = sum(m.seconds for m in working)
    if busy_s < cfg.underused_min_hours * 3600:
        return None
    avg = sum((m.util_avg or 0) * m.seconds for m in working) / busy_s
    if avg >= cfg.underused_util_pct:
        return None
    return Finding(
        kind="underused",
        subject=str(gpu.id),
        severity="info",
        title=f"Running at {avg:.0f}% utilization while busy",
        summary=(
            f"When work was running on {gpu.label} ({gpu.name}), average utilization was "
            f"{avg:.0f}% over {hours(busy_s)}. Most of the GPU's compute sat unused."
        ),
        recommendation=(
            "Raise the batch size or concurrency, check for input pipeline stalls (data "
            "loading, CPU preprocessing), or share the GPU between workloads (MIG, MPS, or "
            "several model replicas)."
        ),
        window_start=window[0],
        window_end=window[1],
        evidence={
            "busy_hours": round(busy_s / 3600, 3),
            "avg_util": round(avg, 2),
            "threshold_pct": cfg.underused_util_pct,
        },
        host_id=gpu.host_id,
        gpu_id=gpu.id,
    )


def oversized_finding(
    gpu: GpuContext,
    minutes: Sequence[Minute],
    cfg: InsightSettings,
    window: tuple[datetime, datetime],
    catalog: Sequence[CatalogEntry],
) -> Finding | None:
    total = gpu.memory_total_mib or next((m.mem_total for m in minutes if m.mem_total), None)
    used = [m.mem_used_max for m in minutes if m.mem_used_max is not None]
    monitored = sum(m.seconds for m in minutes)
    if not total or not used or monitored < 86400 or not any(m.procs_max for m in minutes):
        return None
    peak = max(used)
    if 100 * peak / total >= cfg.oversized_peak_pct:
        return None
    evidence: dict[str, Any] = {
        "peak_mib": round(peak, 1),
        "total_mib": round(total, 1),
        "peak_pct": round(100 * peak / total, 2),
        "monitored_hours": round(monitored / 3600, 3),
    }
    est = None
    candidate = None
    if gpu.nusd_per_hour is not None:
        # GeForce cards are not licensed for data centre use: never suggest one for a
        # data centre GPU.
        consumer_ok = "GeForce" in gpu.name
        options = [
            c
            for c in catalog
            if c.model != gpu.name
            and c.memory_total_mib >= peak * 1.25
            and c.nusd_per_hour < gpu.nusd_per_hour
            and (consumer_ok or "GeForce" not in c.model)
        ]
        if options:
            candidate = min(options, key=lambda c: c.nusd_per_hour)
            est = (gpu.nusd_per_hour - candidate.nusd_per_hour) * HOURS_PER_MONTH
            evidence["candidate"] = {
                "model": candidate.model,
                "memory_total_mib": candidate.memory_total_mib,
                "nusd_per_hour": candidate.nusd_per_hour,
            }
    move = (
        f" It would fit with headroom on a {candidate.model.removeprefix('NVIDIA ')} "
        f"({gib(candidate.memory_total_mib)}, {usd(candidate.nusd_per_hour)}/h at your rates)."
        if candidate
        else ""
    )
    return Finding(
        kind="oversized_vram",
        subject=str(gpu.id),
        severity="info",
        title=f"Peak memory {gib(peak)} of {gib(total)}",
        summary=(
            f"Over {hours(monitored)} of data, {gpu.label} ({gpu.name}) never used more than "
            f"{100 * peak / total:.0f}% of its memory.{move}"
        ),
        recommendation=(
            "If this workload is steady, run it on a GPU with less memory, or pack more work "
            "onto this one (more replicas, larger batches)."
        ),
        window_start=window[0],
        window_end=window[1],
        evidence=evidence,
        est_monthly_nusd=est,
        host_id=gpu.host_id,
        gpu_id=gpu.id,
    )


# ── health (last 24 hours) ───────────────────────────────────────────────────

_THROTTLE_TEXT = {
    "power": (
        "power cap",
        "Check the power limit (nvidia-smi -q -d POWER) and the PSU; a raised limit or "
        "better power delivery restores clocks.",
    ),
    "thermal": (
        "thermal limit",
        "Improve cooling: airflow, fan curve, dust, ambient temperature, or spacing between cards.",
    ),
    "hw": (
        "hardware slowdown",
        "A hardware slowdown usually means overheating or a power brake signal; check "
        "cooling, power cables and the system event log.",
    ),
}


def throttle_finding(
    gpu: GpuContext,
    minutes: Sequence[Minute],
    cfg: InsightSettings,
    window: tuple[datetime, datetime],
) -> Finding | None:
    with_reasons = [m for m in minutes if m.busy_s is not None and m.throttle_power_s is not None]
    busy = sum(m.busy_s or 0 for m in with_reasons)
    if busy < 1800:
        return None
    shares = {
        "power": sum(m.throttle_power_s or 0 for m in with_reasons) / busy,
        "thermal": sum(m.throttle_thermal_s or 0 for m in with_reasons) / busy,
        "hw": sum(m.throttle_hw_s or 0 for m in with_reasons) / busy,
    }
    hit = {k: v for k, v in shares.items() if v * 100 >= cfg.throttle_pct}
    if not hit:
        return None
    main = max(hit, key=lambda k: hit[k])
    name, fix = _THROTTLE_TEXT[main]
    others = [f"{_THROTTLE_TEXT[k][0]} {v:.0%}" for k, v in hit.items() if k != main]
    severe = main in ("thermal", "hw") and hit[main] >= 0.25
    return Finding(
        kind="throttled",
        subject=str(gpu.id),
        severity="critical" if severe else "warning",
        title=f"Slowed by {name} {hit[main]:.0%} of busy time",
        summary=(
            f"{gpu.label} ({gpu.name}) ran below full clocks because of its {name} for "
            f"{hit[main]:.0%} of {hours(busy)} of busy time"
            + (f" (also {', '.join(others)})" if others else "")
            + ". Work there takes longer than it should."
        ),
        recommendation=fix,
        window_start=window[0],
        window_end=window[1],
        evidence={
            "busy_hours": round(busy / 3600, 3),
            "shares": {k: round(v, 4) for k, v in shares.items()},
            "main_reason": main,
        },
        host_id=gpu.host_id,
        gpu_id=gpu.id,
    )


def memory_pressure_finding(
    gpu: GpuContext,
    minutes: Sequence[Minute],
    cfg: InsightSettings,
    window: tuple[datetime, datetime],
) -> Finding | None:
    full = [
        m
        for m in minutes
        if m.mem_used_max is not None
        and m.mem_total
        and 100 * m.mem_used_max / m.mem_total >= cfg.mem_pressure_pct
    ]
    if len(full) < cfg.mem_pressure_minutes:
        return None
    peak = max(m.mem_used_max or 0 for m in full)
    total = next(m.mem_total for m in full if m.mem_total)
    return Finding(
        kind="memory_pressure",
        subject=str(gpu.id),
        severity="warning",
        title=f"Memory above {cfg.mem_pressure_pct:g}% for {len(full)} min",
        summary=(
            f"{gpu.label} ({gpu.name}) used {cfg.mem_pressure_pct:g}% or more of its memory for "
            f"{len(full)} minutes (peak {gib(peak)} of {gib(total or 0)}). The next larger "
            "batch or a longer context can fail with an out-of-memory error."
        ),
        recommendation=(
            "Lower the batch size or maximum context length, enable memory-efficient "
            "attention or quantization, or move the workload to a GPU with more memory."
        ),
        window_start=window[0],
        window_end=window[1],
        evidence={"minutes": len(full), "peak_mib": round(peak, 1), "total_mib": total},
        host_id=gpu.host_id,
        gpu_id=gpu.id,
    )


def errors_finding(
    gpu: GpuContext, minutes: Sequence[Minute], window: tuple[datetime, datetime]
) -> Finding | None:
    ecc = [m.ecc_max for m in minutes if m.ecc_max is not None]
    ecc_new = (max(ecc) - min(ecc)) if len(ecc) >= 2 else 0
    xids = sum(m.xid_count for m in minutes)
    if ecc_new <= 0 and xids <= 0:
        return None
    parts = []
    if ecc_new > 0:
        parts.append(f"{ecc_new} new uncorrected ECC error{'s' if ecc_new != 1 else ''}")
    if xids > 0:
        parts.append(f"{xids} XID event{'s' if xids != 1 else ''}")
    return Finding(
        kind="gpu_errors",
        subject=str(gpu.id),
        severity="critical",
        title="Hardware errors reported",
        summary=f"The driver reported {' and '.join(parts)} on {gpu.label} ({gpu.name}).",
        recommendation=(
            "Check the XID codes in the kernel log (dmesg | grep -i xid). Repeated uncorrected "
            "ECC errors usually need a GPU reset or replacement; drain work from this GPU."
        ),
        window_start=window[0],
        window_end=window[1],
        evidence={"ecc_new": ecc_new, "xid_events": xids},
        host_id=gpu.host_id,
        gpu_id=gpu.id,
    )


def evaluate_gpu(
    gpu: GpuContext,
    minutes: Sequence[Minute],
    cfg: InsightSettings,
    window: tuple[datetime, datetime],
    catalog: Sequence[CatalogEntry],
) -> list[Finding]:
    """Every finding for one GPU. ``minutes`` must be sorted and cover ``window``; health
    rules use only its last 24 hours."""
    found = idle_findings(gpu, minutes, cfg, window)
    for f in (
        underused_finding(gpu, minutes, cfg, window),
        oversized_finding(gpu, minutes, cfg, window, catalog),
    ):
        if f:
            found.append(f)
    day_start = window[1] - timedelta(days=1)
    recent = [m for m in minutes if m.bucket >= day_start]
    day = (max(day_start, window[0]), window[1])
    for f in (
        throttle_finding(gpu, recent, cfg, day),
        memory_pressure_finding(gpu, recent, cfg, day),
        errors_finding(gpu, recent, day),
    ):
        if f:
            found.append(f)
    return found


# ── inference ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EndpointMinute:
    bucket: datetime
    requests: float | None
    waiting: float | None
    kv_cache: float | None


@dataclass(frozen=True, slots=True)
class EndpointContext:
    id: uuid.UUID
    host_id: uuid.UUID
    name: str
    kind: str
    model: str | None
    gpu_util_avg: float | None
    tokens: float
    cost_nusd: int | None


def inference_findings(
    ep: EndpointContext,
    minutes: Iterable[EndpointMinute],
    cfg: InsightSettings,
    window: tuple[datetime, datetime],
) -> list[Finding]:
    rows = list(minutes)
    out = []
    queued = [
        m
        for m in rows
        if (m.waiting or 0) > 0 and m.kv_cache is not None and m.kv_cache >= cfg.kv_cache_full
    ]
    if len(queued) >= cfg.queue_minutes:
        out.append(
            Finding(
                kind="inference_queueing",
                subject=str(ep.id),
                severity="warning",
                title=f"Requests queued with the KV cache full for {len(queued)} min",
                summary=(
                    f"{ep.name} ({ep.kind}) had requests waiting while its KV cache was at "
                    f"{cfg.kv_cache_full:.0%} or more for {len(queued)} minutes. Latency rises "
                    "because the server cannot admit more sequences."
                ),
                recommendation=(
                    "Add a replica or a GPU, lower the maximum context length, or enable a "
                    "quantized KV cache so more sequences fit."
                ),
                window_start=window[0],
                window_end=window[1],
                evidence={"minutes": len(queued), "kv_cache_threshold": cfg.kv_cache_full},
                host_id=ep.host_id,
                endpoint_id=ep.id,
            )
        )
    requests = sum(m.requests or 0 for m in rows)
    if (
        requests > 0
        and ep.gpu_util_avg is not None
        and ep.gpu_util_avg < cfg.overprovisioned_util_pct
    ):
        per_m = (
            round(ep.cost_nusd * 1e6 / ep.tokens)
            if ep.cost_nusd is not None and ep.tokens > 0
            else None
        )
        price = f" Cost per million tokens was {usd(per_m)}." if per_m is not None else ""
        out.append(
            Finding(
                kind="inference_overprovisioned",
                subject=str(ep.id),
                severity="info",
                title=f"Serving at {ep.gpu_util_avg:.0f}% GPU utilization",
                summary=(
                    f"{ep.name} served {requests:,.0f} requests but its GPUs averaged "
                    f"{ep.gpu_util_avg:.0f}% utilization.{price}"
                ),
                recommendation=(
                    "Fewer or smaller GPUs would serve this traffic: consolidate replicas, or "
                    "co-locate another model on the same GPU."
                ),
                window_start=window[0],
                window_end=window[1],
                evidence={
                    "requests": requests,
                    "gpu_util_avg": round(ep.gpu_util_avg, 2),
                    "tokens": ep.tokens,
                    "cost_nusd": ep.cost_nusd,
                    "nusd_per_million_tokens": per_m,
                },
                host_id=ep.host_id,
                endpoint_id=ep.id,
            )
        )
    return out

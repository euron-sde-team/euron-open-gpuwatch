"""History queries. The resolution follows the range so a chart never pulls more than a
few thousand points: raw samples up to 3 hours, minute buckets up to 3 days, hours beyond.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.core.container import Container
from gpuwatch.core.errors import AppError, NotFoundError
from gpuwatch.costs.attribution import UNATTRIBUTED, Proc, classify, compile_rules
from gpuwatch.costs.models import IDLE_WORKLOAD, WorkloadRule
from gpuwatch.fleet.models import Gpu, Host
from gpuwatch.telemetry.models import THROTTLE_HW, THROTTLE_POWER, THROTTLE_THERMAL
from gpuwatch.telemetry.schemas import (
    FleetPoint,
    FleetSeries,
    GpuProcesses,
    MetricPoint,
    MetricSeries,
    ProcessOut,
    Resolution,
    WorkloadShare,
)

MAX_RANGE = timedelta(days=400)
_METRICS = (
    "util",
    "util_mem",
    "mem_used_mib",
    "temp_c",
    "power_w",
    "fan_pct",
    "sm_clock_mhz",
    "procs",
    "throttle_power",
)


def resolution_for(start: datetime, end: datetime) -> Resolution:
    span = end - start
    if span <= timedelta(hours=3):
        return "raw"
    if span <= timedelta(days=3):
        return "1m"
    return "1h"


def _check(start: datetime, end: datetime) -> None:
    if end <= start:
        raise AppError("The end must be after the start", code="invalid_range")
    if end - start > MAX_RANGE:
        raise AppError("Choose a range of at most 400 days", code="range_too_long")


_RAW = text(
    f"""
    SELECT ts, util_gpu AS util, util_gpu AS util_max, util_mem, mem_used_mib,
           mem_used_mib AS mem_used_max_mib, mem_total_mib, temp_c, temp_c AS temp_max_c,
           power_w, power_w AS power_max_w, fan_pct, sm_clock_mhz, procs,
           CASE WHEN throttle_reasons IS NULL THEN NULL
                WHEN util_gpu >= 50 AND throttle_reasons & {THROTTLE_POWER} <> 0 THEN 1.0
                ELSE 0.0 END AS throttle_power,
           CASE WHEN throttle_reasons IS NULL THEN NULL
                WHEN util_gpu >= 50 AND throttle_reasons & {THROTTLE_THERMAL} <> 0 THEN 1.0
                ELSE 0.0 END AS throttle_thermal,
           CASE WHEN throttle_reasons IS NULL THEN NULL
                WHEN util_gpu >= 50 AND throttle_reasons & {THROTTLE_HW} <> 0 THEN 1.0
                ELSE 0.0 END AS throttle_hw
    FROM gpu_samples WHERE gpu_id = :gpu AND ts >= :start AND ts < :end ORDER BY ts
    """
)


def _rollup_sql(table: str) -> str:
    return f"""
    SELECT bucket AS ts, util_avg AS util, util_max, util_mem_avg AS util_mem,
           mem_used_avg AS mem_used_mib, mem_used_max AS mem_used_max_mib,
           mem_total AS mem_total_mib, temp_avg AS temp_c, temp_max AS temp_max_c,
           power_avg AS power_w, power_max AS power_max_w, fan_avg AS fan_pct, sm_clock_avg
           AS sm_clock_mhz, procs_max AS procs,
           throttle_power_s / nullif(busy_s, 0) AS throttle_power,
           throttle_thermal_s / nullif(busy_s, 0) AS throttle_thermal,
           throttle_hw_s / nullif(busy_s, 0) AS throttle_hw
    FROM {table} WHERE gpu_id = :gpu AND bucket >= :start AND bucket < :end ORDER BY bucket
    """


_ROLLUP = {"1m": text(_rollup_sql("gpu_rollups_1m")), "1h": text(_rollup_sql("gpu_rollups_1h"))}


async def gpu_series(
    session: AsyncSession,
    gpu_id: uuid.UUID,
    start: datetime,
    end: datetime,
    resolution: Resolution | None,
) -> MetricSeries:
    _check(start, end)
    if await session.get(Gpu, gpu_id) is None:
        raise NotFoundError("GPU not found")
    res = resolution or resolution_for(start, end)
    sql = _RAW if res == "raw" else _ROLLUP[res]
    rows = (
        (await session.execute(sql, {"gpu": gpu_id, "start": start, "end": end})).mappings().all()
    )
    points = [MetricPoint(**dict(r)) for r in rows]
    available = [m for m in _METRICS if any(getattr(p, m) is not None for p in points)]
    return MetricSeries(
        gpu_id=gpu_id, start=start, end=end, resolution=res, points=points, available=available
    )


def _fleet_sql(table: str, bucket: str) -> str:
    raw = table == "gpu_samples"
    util, mem, power, ts = (
        ("util_gpu", "mem_used_mib / nullif(mem_total_mib, 0)", "power_w", "ts")
        if raw
        else ("util_avg", "mem_used_avg / nullif(mem_total, 0)", "power_avg", "bucket")
    )
    # Per GPU and bucket first (a GPU reports many raw samples per minute), then across GPUs.
    return f"""
    SELECT b AS ts, avg(util) AS util_avg, avg(mem_pct) AS mem_pct_avg,
           sum(power) AS power_w, count(*) AS gpus
    FROM (
        SELECT gpu_id, {bucket} AS b, avg({util}) AS util, avg(100.0 * {mem}) AS mem_pct,
               avg({power}) AS power
        FROM {table}
        WHERE {ts} >= :start AND {ts} < :end
          AND (CAST(:host AS uuid) IS NULL OR host_id = :host)
        GROUP BY gpu_id, b
    ) per_gpu
    GROUP BY b ORDER BY b
    """


_FLEET = {
    "raw": text(_fleet_sql("gpu_samples", "date_trunc('minute', ts)")),
    "1m": text(
        _fleet_sql(
            "gpu_rollups_1m",
            "date_trunc('hour', bucket) + floor(extract(minute FROM bucket) / 10)"
            " * interval '10 minutes'",
        )
    ),
    "1h": text(_fleet_sql("gpu_rollups_1h", "bucket")),
}


async def fleet_series(
    session: AsyncSession, start: datetime, end: datetime, host_id: uuid.UUID | None
) -> FleetSeries:
    """Fleet-wide utilization, memory and power: per minute up to 3 hours, per 10 minutes up
    to 3 days, per hour beyond. A GPU that did not report in a bucket is not averaged in."""
    _check(start, end)
    res = resolution_for(start, end)
    rows = (
        (await session.execute(_FLEET[res], {"start": start, "end": end, "host": host_id}))
        .mappings()
        .all()
    )
    points = [
        FleetPoint(
            ts=r["ts"],
            util_avg=float(r["util_avg"]) if r["util_avg"] is not None else None,
            mem_pct_avg=float(r["mem_pct_avg"]) if r["mem_pct_avg"] is not None else None,
            power_w=float(r["power_w"]) if r["power_w"] is not None else None,
            gpus=int(r["gpus"]),
        )
        for r in rows
    ]
    return FleetSeries(start=start, end=end, resolution=res, points=points)


_CURRENT = text(
    """
    SELECT pid, name, username, container_id, mem_used_mib, sm_util, ts FROM process_samples
    WHERE gpu_id = :gpu AND ts = (
        SELECT max(ts) FROM gpu_samples
        WHERE gpu_id = :gpu AND ts > now() - make_interval(secs => :ttl)
    )
    ORDER BY mem_used_mib DESC NULLS LAST
    """
)
_LAST_SAMPLE = text(
    "SELECT ts, procs FROM gpu_samples WHERE gpu_id = :gpu "
    "AND ts > now() - make_interval(secs => :ttl) ORDER BY ts DESC LIMIT 1"
)
_WORKLOADS = text(
    """
    SELECT workload, max(team) AS team, sum(seconds) AS seconds, sum(idle_seconds) AS idle
    FROM workload_usage_1h WHERE gpu_id = :gpu AND bucket >= :start
    GROUP BY workload ORDER BY sum(seconds) DESC
    """
)


async def gpu_processes(
    session: AsyncSession, container: Container, gpu_id: uuid.UUID, window_hours: int = 24
) -> GpuProcesses:
    gpu = await session.get(Gpu, gpu_id)
    if gpu is None:
        raise NotFoundError("GPU not found")
    host = await session.get(Host, gpu.host_id)
    params: dict[str, Any] = {"gpu": gpu_id, "ttl": container.settings.live_ttl_s}
    last = (await session.execute(_LAST_SAMPLE, params)).first()
    rows = (await session.execute(_CURRENT, params)).all()
    rules = compile_rules((await session.scalars(select(WorkloadRule))).all())
    labels = host.labels if host else {}
    current = []
    for pid, name, username, container_id, mem, sm, _ts in rows:
        workload, team = classify(Proc(pid, name, username, container_id, mem, sm), rules, labels)
        current.append(
            ProcessOut(
                pid=pid,
                name=name,
                username=username,
                container_id=container_id,
                mem_used_mib=mem,
                sm_util=sm,
                workload=workload,
                team=team,
            )
        )
    start = datetime.now(UTC) - timedelta(hours=window_hours)
    usage = (await session.execute(_WORKLOADS, {"gpu": gpu_id, "start": start})).all()
    total = sum(float(r.seconds) for r in usage) or 0.0
    workloads = [
        WorkloadShare(
            workload=r.workload,
            label="Idle (nothing running)"
            if r.workload == IDLE_WORKLOAD
            else (
                "Unattributed (driver lists no processes)"
                if r.workload == UNATTRIBUTED
                else r.workload
            ),
            team=r.team,
            gpu_hours=round(float(r.seconds) / 3600, 3),
            idle_hours=round(float(r.idle) / 3600, 3),
            share=float(r.seconds) / total if total else 0.0,
        )
        for r in usage
    ]
    return GpuProcesses(
        gpu_id=gpu_id,
        at=last.ts if last else None,
        listed=not (last is not None and last.procs is None),
        current=current,
        window_hours=window_hours,
        workloads=workloads,
    )

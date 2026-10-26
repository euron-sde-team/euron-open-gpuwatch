"""Rollups: raw samples to 1-minute buckets to 1-hour buckets.

Every recompute is an idempotent upsert of whole buckets from their source rows, so running
a range twice gives the same result. Two paths feed it:

* the watermark: each tick closes the minutes between the last watermark and
  ``now - ROLLUP_LAG_S`` (late rows within the lag are included naturally);
* dirty ranges: ingest records the range of rows older than the watermark (a spool replay
  after an outage, a demo backfill), and the next tick recomputes exactly that range.

After the minute buckets of a range change, the hours that contain them are recomputed,
then cost attribution and inference rollups for those hours.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from gpuwatch.core.container import Container
from gpuwatch.telemetry.models import (
    THROTTLE_HW,
    THROTTLE_POWER,
    THROTTLE_THERMAL,
    JobState,
    RollupDirty,
)

log = logging.getLogger("gpuwatch.rollups")
JOB = "rollup"
BUSY_UTIL = 50.0  # utilization at or above which a GPU counts as busy
# Process at most this much history per transaction (a 30-day backfill runs in steps).
STEP = timedelta(hours=6)

_MINUTES = text(
    f"""
    INSERT INTO gpu_rollups_1m AS r (
        gpu_id, bucket, host_id, samples, seconds, util_avg, util_max, util_mem_avg,
        mem_used_avg, mem_used_max, mem_total, temp_avg, temp_max, power_avg, power_max,
        energy_wh, fan_avg, sm_clock_avg, busy_s, throttle_power_s, throttle_thermal_s,
        throttle_hw_s, procs_max, ecc_max, xid_count)
    SELECT gpu_id, date_trunc('minute', ts), host_id, count(*), sum(interval_s),
        avg(util_gpu), max(util_gpu), avg(util_mem), avg(mem_used_mib), max(mem_used_mib),
        max(mem_total_mib), avg(temp_c), max(temp_c), avg(power_w), max(power_w),
        sum(power_w * interval_s) / 3600.0, avg(fan_pct), avg(sm_clock_mhz),
        CASE WHEN count(util_gpu) = 0 THEN NULL
             ELSE coalesce(sum(interval_s) FILTER (WHERE util_gpu >= {BUSY_UTIL}), 0) END,
        CASE WHEN count(throttle_reasons) = 0 THEN NULL
             ELSE coalesce(sum(interval_s) FILTER (WHERE util_gpu >= {BUSY_UTIL}
                  AND throttle_reasons & {THROTTLE_POWER} <> 0), 0) END,
        CASE WHEN count(throttle_reasons) = 0 THEN NULL
             ELSE coalesce(sum(interval_s) FILTER (WHERE util_gpu >= {BUSY_UTIL}
                  AND throttle_reasons & {THROTTLE_THERMAL} <> 0), 0) END,
        CASE WHEN count(throttle_reasons) = 0 THEN NULL
             ELSE coalesce(sum(interval_s) FILTER (WHERE util_gpu >= {BUSY_UTIL}
                  AND throttle_reasons & {THROTTLE_HW} <> 0), 0) END,
        max(procs), max(ecc_uncorrected), count(*) FILTER (WHERE xid > 0)
    FROM gpu_samples
    WHERE ts >= :start AND ts < :end AND (CAST(:host AS uuid) IS NULL OR host_id = :host)
    GROUP BY gpu_id, date_trunc('minute', ts), host_id
    ON CONFLICT (gpu_id, bucket) DO UPDATE SET
        host_id = excluded.host_id, samples = excluded.samples, seconds = excluded.seconds,
        util_avg = excluded.util_avg, util_max = excluded.util_max,
        util_mem_avg = excluded.util_mem_avg, mem_used_avg = excluded.mem_used_avg,
        mem_used_max = excluded.mem_used_max, mem_total = excluded.mem_total,
        temp_avg = excluded.temp_avg, temp_max = excluded.temp_max,
        power_avg = excluded.power_avg, power_max = excluded.power_max,
        energy_wh = excluded.energy_wh, fan_avg = excluded.fan_avg,
        sm_clock_avg = excluded.sm_clock_avg, busy_s = excluded.busy_s,
        throttle_power_s = excluded.throttle_power_s,
        throttle_thermal_s = excluded.throttle_thermal_s,
        throttle_hw_s = excluded.throttle_hw_s, procs_max = excluded.procs_max,
        ecc_max = excluded.ecc_max, xid_count = excluded.xid_count
    """
)


def _wavg(col: str) -> str:
    """Seconds-weighted average over the minutes that reported the metric."""
    return (
        f"sum({col} * seconds) FILTER (WHERE {col} IS NOT NULL)"
        f" / nullif(sum(seconds) FILTER (WHERE {col} IS NOT NULL), 0)"
    )


_HOURS = text(
    f"""
    INSERT INTO gpu_rollups_1h AS r (
        gpu_id, bucket, host_id, samples, seconds, util_avg, util_max, util_mem_avg,
        mem_used_avg, mem_used_max, mem_total, temp_avg, temp_max, power_avg, power_max,
        energy_wh, fan_avg, sm_clock_avg, busy_s, throttle_power_s, throttle_thermal_s,
        throttle_hw_s, procs_max, ecc_max, xid_count)
    SELECT gpu_id, date_trunc('hour', bucket), max(host_id::text)::uuid, sum(samples),
        sum(seconds), {_wavg("util_avg")}, max(util_max), {_wavg("util_mem_avg")},
        {_wavg("mem_used_avg")}, max(mem_used_max), max(mem_total), {_wavg("temp_avg")},
        max(temp_max), {_wavg("power_avg")}, max(power_max), sum(energy_wh),
        {_wavg("fan_avg")}, {_wavg("sm_clock_avg")}, sum(busy_s), sum(throttle_power_s),
        sum(throttle_thermal_s), sum(throttle_hw_s), max(procs_max), max(ecc_max),
        sum(xid_count)
    FROM gpu_rollups_1m
    WHERE bucket >= :start AND bucket < :end AND (CAST(:host AS uuid) IS NULL OR host_id = :host)
    GROUP BY gpu_id, date_trunc('hour', bucket)
    ON CONFLICT (gpu_id, bucket) DO UPDATE SET
        host_id = excluded.host_id, samples = excluded.samples, seconds = excluded.seconds,
        util_avg = excluded.util_avg, util_max = excluded.util_max,
        util_mem_avg = excluded.util_mem_avg, mem_used_avg = excluded.mem_used_avg,
        mem_used_max = excluded.mem_used_max, mem_total = excluded.mem_total,
        temp_avg = excluded.temp_avg, temp_max = excluded.temp_max,
        power_avg = excluded.power_avg, power_max = excluded.power_max,
        energy_wh = excluded.energy_wh, fan_avg = excluded.fan_avg,
        sm_clock_avg = excluded.sm_clock_avg, busy_s = excluded.busy_s,
        throttle_power_s = excluded.throttle_power_s,
        throttle_thermal_s = excluded.throttle_thermal_s,
        throttle_hw_s = excluded.throttle_hw_s, procs_max = excluded.procs_max,
        ecc_max = excluded.ecc_max, xid_count = excluded.xid_count
    """
)


def floor_minute(t: datetime) -> datetime:
    return t.replace(second=0, microsecond=0)


def floor_hour(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


def ceil_hour(t: datetime) -> datetime:
    h = floor_hour(t)
    return h if h == t else h + timedelta(hours=1)


async def recompute(
    container: Container, start: datetime, end: datetime, host_id: uuid.UUID | None = None
) -> None:
    """Rebuild minute buckets in [start, end) (whole minutes), the hours containing them,
    and the attribution and inference rollups of those hours."""
    from gpuwatch.costs import attribution
    from gpuwatch.inference import rollups as inference_rollups

    start, end = floor_minute(start), floor_minute(end - timedelta(microseconds=1))
    end += timedelta(minutes=1)
    cursor = start
    while cursor < end:
        step_end = min(end, cursor + STEP)
        async with container.db.engine.begin() as conn:
            await conn.execute(_MINUTES, {"start": cursor, "end": step_end, "host": host_id})
            h_start, h_end = floor_hour(cursor), ceil_hour(step_end)
            await conn.execute(_HOURS, {"start": h_start, "end": h_end, "host": host_id})
            await attribution.recompute(conn, h_start, h_end, host_id)
            await inference_rollups.recompute(conn, h_start, h_end, host_id)
        cursor = step_end


async def _state(conn: AsyncConnection) -> datetime | None:
    return await conn.scalar(
        select(JobState.watermark).where(JobState.name == JOB).with_for_update()
    )


async def tick(container: Container, now: datetime | None = None) -> int:
    """Advance the watermark, then work through dirty ranges. Returns ranges processed."""
    now = now or datetime.now(UTC)
    target = floor_minute(now - timedelta(seconds=container.settings.rollup_lag_s))
    done = 0
    async with container.db.engine.begin() as conn:
        # One rollup worker at a time across replicas; others skip this tick.
        if not await conn.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtext('gpuwatch:rollup'))")
        ):
            return 0
        watermark = await _state(conn)
        if watermark is None:
            # First run: start from the oldest raw sample (or the target, if none yet).
            oldest = await conn.scalar(text("SELECT min(ts) FROM gpu_samples"))
            watermark = floor_minute(oldest) if oldest else target
            await conn.execute(
                insert(JobState).values(name=JOB, watermark=watermark).on_conflict_do_nothing()
            )
        if target > watermark:
            await recompute(container, watermark, target)
            await conn.execute(
                insert(JobState)
                .values(name=JOB, watermark=target, ran_at=now)
                .on_conflict_do_update(
                    index_elements=[JobState.name], set_={"watermark": target, "ran_at": now}
                )
            )
            done += 1
        dirty = (
            await conn.execute(
                select(RollupDirty.id, RollupDirty.host_id, RollupDirty.from_ts, RollupDirty.to_ts)
                .order_by(RollupDirty.id)
                .limit(500)
            )
        ).all()
        # Recompute first, delete after: a crash in between leaves the ranges queued.
        for host_id, (start, end) in _merge([(h, f, t) for _, h, f, t in dirty]).items():
            await recompute(container, start, end, host_id)
            done += 1
        if dirty:
            await conn.execute(delete(RollupDirty).where(RollupDirty.id.in_([d[0] for d in dirty])))
    return done


def _merge(
    rows: list[tuple[uuid.UUID, datetime, datetime]],
) -> dict[uuid.UUID, tuple[datetime, datetime]]:
    """One covering range per host (dirty ranges of one host are usually contiguous)."""
    out: dict[uuid.UUID, list[datetime]] = defaultdict(list)
    for host_id, start, end in rows:
        span = out[host_id]
        if not span:
            span.extend([start, end])
        else:
            span[0], span[1] = min(span[0], start), max(span[1], end)
    return {h: (s[0], s[1]) for h, s in out.items()}

"""Store one agent batch: idempotent, bounded in time, one transaction.

Order of work: refuse a replayed batch id, update the host and its GPU inventory, drop rows
outside the accepted time window or for GPUs the batch did not declare, bulk insert samples,
processes and inference rows, and queue a rollup range for rows old enough that the rollup
job may already have closed their minutes. After the commit, the newest sample of each GPU
goes to the live view.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.core.container import Container
from gpuwatch.core.errors import AppError
from gpuwatch.fleet.models import Gpu, Host
from gpuwatch.inference.models import InferenceEndpoint, InferenceSample
from gpuwatch.ingest.dependencies import AgentHost
from gpuwatch.ingest.schemas import Batch, BatchAccepted, GpuSampleIn
from gpuwatch.observability import metrics
from gpuwatch.telemetry import live, partitions
from gpuwatch.telemetry.models import (
    GpuSample,
    IngestBatch,
    ProcessSample,
    RollupDirty,
)

_SAMPLE_FIELDS = tuple(f for f in GpuSampleIn.model_fields if f not in ("gpu_uuid", "ts"))


def _window(container: Container, host: AgentHost, now: datetime) -> tuple[datetime, datetime]:
    s = container.settings
    days = s.simulated_backfill_days if host.simulated else s.raw_retention_days
    return now - timedelta(days=days), now + timedelta(seconds=s.ingest_max_future_s)


async def store(container: Container, host: AgentHost, batch: Batch) -> BatchAccepted:
    started = time.perf_counter()
    s = container.settings
    total = len(batch.samples) + len(batch.processes) + len(batch.inference)
    if total > s.ingest_max_samples:
        metrics.INGEST_BATCHES.labels("too_large").inc()
        raise AppError(
            f"A batch may carry at most {s.ingest_max_samples} rows; split it",
            code="batch_too_large",
            details={"rows": total, "limit": s.ingest_max_samples},
        )
    now = datetime.now(UTC)
    oldest, newest = _window(container, host, now)
    samples = [r for r in batch.samples if oldest <= r.ts <= newest]
    processes = [r for r in batch.processes if oldest <= r.ts <= newest]
    inference = [r for r in batch.inference if oldest <= r.ts <= newest]
    out_of_window = total - len(samples) - len(processes) - len(inference)
    if out_of_window:
        metrics.INGEST_DROPPED.labels("time_window").inc(out_of_window)

    days: set[date] = {r.ts.astimezone(UTC).date() for r in samples}
    days |= {r.ts.astimezone(UTC).date() for r in processes}
    await partitions.ensure(container.db.engine, days)

    async with container.db.sessionmaker() as session:
        first = await session.scalar(
            insert(IngestBatch)
            .values(host_id=host.id, batch_id=batch.batch_id)
            .on_conflict_do_nothing()
            .returning(IngestBatch.batch_id)
        )
        if first is None:
            await session.rollback()
            metrics.INGEST_BATCHES.labels("duplicate").inc()
            return BatchAccepted(
                accepted=True,
                duplicate=True,
                samples=0,
                processes=0,
                inference=0,
                dropped=0,
                next_in_s=batch.agent.interval_s,
            )
        await _update_host(session, host, batch, now)
        gpu_ids = await _upsert_gpus(session, host, batch, now)
        sample_rows = [_sample_row(r, gpu_ids, host.id) for r in samples if r.gpu_uuid in gpu_ids]
        process_rows = [
            {
                "gpu_id": gpu_ids[r.gpu_uuid],
                "host_id": host.id,
                "ts": r.ts,
                "pid": r.pid,
                "name": r.name,
                "username": r.username,
                "container_id": r.container_id,
                "mem_used_mib": r.mem_used_mib,
                "sm_util": r.sm_util,
            }
            for r in processes
            if r.gpu_uuid in gpu_ids
        ]
        unknown = len(samples) - len(sample_rows) + len(processes) - len(process_rows)
        if unknown:
            metrics.INGEST_DROPPED.labels("unknown_gpu").inc(unknown)
        # executemany: one cached statement, rows batched by the driver. Building a
        # multi-row VALUES clause per batch instead costs seconds of CPU on large batches.
        if sample_rows:
            await session.execute(insert(GpuSample).on_conflict_do_nothing(), sample_rows)
        if process_rows:
            await session.execute(insert(ProcessSample).on_conflict_do_nothing(), process_rows)
        n_inference = await _store_inference(session, host, batch, inference, gpu_ids)
        await _mark_dirty(session, host.id, sample_rows, now, s.rollup_lag_s)
        await session.commit()

    metrics.INGEST_ROWS.labels("gpu_samples").inc(len(sample_rows))
    metrics.INGEST_ROWS.labels("process_samples").inc(len(process_rows))
    metrics.INGEST_ROWS.labels("inference_samples").inc(n_inference)
    await live.publish(container, _latest(sample_rows, now, s.live_ttl_s))
    metrics.INGEST_BATCHES.labels("accepted").inc()
    metrics.INGEST_SECONDS.observe(time.perf_counter() - started)
    return BatchAccepted(
        accepted=True,
        duplicate=False,
        samples=len(sample_rows),
        processes=len(process_rows),
        inference=n_inference,
        dropped=out_of_window + unknown,
        next_in_s=batch.agent.interval_s,
    )


def _sample_row(
    r: GpuSampleIn, gpu_ids: dict[str, uuid.UUID], host_id: uuid.UUID
) -> dict[str, Any]:
    row: dict[str, Any] = {"gpu_id": gpu_ids[r.gpu_uuid], "host_id": host_id, "ts": r.ts}
    for field in _SAMPLE_FIELDS:
        row[field] = getattr(r, field)
    return row


async def _update_host(session: AsyncSession, host: AgentHost, batch: Batch, now: datetime) -> None:
    a = batch.agent
    row = await session.get(Host, host.id, with_for_update=True)
    if row is None:  # deleted between auth and now
        raise AppError("Unknown host", code="invalid_host_token")
    row.hostname = a.hostname
    row.agent_version = a.version
    row.collector = a.collector
    row.os = a.os
    row.kernel = a.kernel
    row.driver_version = a.driver_version
    row.cuda_version = a.cuda_version
    row.interval_s = a.interval_s
    row.agent_status = a.status
    row.problems = [p.model_dump() for p in a.problems]
    row.first_seen_at = row.first_seen_at or now
    row.last_seen_at = now


async def _upsert_gpus(
    session: AsyncSession, host: AgentHost, batch: Batch, now: datetime
) -> dict[str, uuid.UUID]:
    """Declared GPUs, created or updated; a card that moved hosts follows its UUID."""
    if not batch.gpus:
        return {}
    stmt = insert(Gpu).values(
        [
            {
                "id": uuid.uuid4(),
                "host_id": host.id,
                "uuid": g.uuid,
                "index": g.index,
                "name": g.name,
                "memory_total_mib": g.memory_total_mib,
                "power_limit_w": g.power_limit_w,
                "pci_bus_id": g.pci_bus_id,
                "mig_mode": g.mig_mode,
                "last_seen_at": now,
            }
            for g in {g.uuid: g for g in batch.gpus}.values()
        ]
    )
    upsert = stmt.on_conflict_do_update(
        index_elements=[Gpu.uuid],
        set_={
            "host_id": stmt.excluded.host_id,
            "index": stmt.excluded.index,
            "name": stmt.excluded.name,
            "memory_total_mib": stmt.excluded.memory_total_mib,
            "power_limit_w": stmt.excluded.power_limit_w,
            "pci_bus_id": stmt.excluded.pci_bus_id,
            "mig_mode": stmt.excluded.mig_mode,
            "last_seen_at": stmt.excluded.last_seen_at,
            # A retired GPU that reports again is back in service.
            "retired_at": None,
        },
    ).returning(Gpu.uuid, Gpu.id)
    return {row[0]: row[1] for row in (await session.execute(upsert)).all()}


async def _store_inference(
    session: AsyncSession,
    host: AgentHost,
    batch: Batch,
    rows: list[Any],
    gpu_ids: dict[str, uuid.UUID],
) -> int:
    if not rows:
        return 0
    endpoints: dict[str, uuid.UUID] = {}
    for r in {r.endpoint: r for r in rows}.values():
        values = {
            "host_id": host.id,
            "name": r.endpoint,
            "kind": r.kind,
            "url": r.url,
            "model": r.model,
            "gpu_ids": [str(gpu_ids[u]) for u in r.gpu_uuids if u in gpu_ids],
            "up": r.up,
            "last_seen_at": r.ts,
        }
        ins = insert(InferenceEndpoint).values(id=uuid.uuid4(), **values)
        upsert = ins.on_conflict_do_update(
            constraint="uq_inference_endpoint_name",
            set_={
                **{k: ins.excluded[k] for k in values if k not in ("host_id", "name", "model")},
                # TGI does not put the model in its metrics: keep the last one known.
                "model": func.coalesce(ins.excluded.model, InferenceEndpoint.model),
            },
        ).returning(InferenceEndpoint.id)
        endpoints[r.endpoint] = (await session.execute(upsert)).scalar_one()
    values_list = [
        {
            "endpoint_id": endpoints[r.endpoint],
            "ts": r.ts,
            "interval_s": r.interval_s,
            "up": r.up,
            "requests": r.requests,
            "prompt_tokens": r.prompt_tokens,
            "generation_tokens": r.generation_tokens,
            "running": r.running,
            "waiting": r.waiting,
            "kv_cache_usage": r.kv_cache_usage,
            "ttft": r.ttft,
            "itl": r.itl,
            "e2e": r.e2e,
        }
        for r in rows
    ]
    await session.execute(insert(InferenceSample).on_conflict_do_nothing(), values_list)
    return len(values_list)


async def _mark_dirty(
    session: AsyncSession, host_id: uuid.UUID, rows: list[dict[str, Any]], now: datetime, lag_s: int
) -> None:
    """Queue a rollup range for rows the watermark may already have passed.

    The rollup job closes minutes older than ``now - lag``. Rows older than half the lag
    may land in a range it is closing at this moment, so they are queued as well; recompute
    is idempotent, so a range rolled up twice is harmless. An ingest transaction would have
    to take lag/2 (45 s by default) for a row to slip between the two paths.
    """
    if not rows:
        return
    oldest = min(r["ts"] for r in rows)
    if oldest >= now - timedelta(seconds=lag_s / 2):
        return
    newest = max(r["ts"] for r in rows)
    await session.execute(
        insert(RollupDirty).values(
            host_id=host_id, from_ts=oldest, to_ts=newest + timedelta(seconds=1)
        )
    )


def _latest(
    rows: list[dict[str, Any]], now: datetime, ttl_s: int
) -> dict[uuid.UUID, dict[str, Any]]:
    """Each GPU's newest row, if recent enough to be "live" (a backfill is not)."""
    newest: dict[uuid.UUID, dict[str, Any]] = {}
    for r in rows:
        if now - r["ts"] > timedelta(seconds=ttl_s):
            continue
        cur = newest.get(r["gpu_id"])
        if cur is None or r["ts"] > cur["ts"]:
            newest[r["gpu_id"]] = r
    return {
        gpu_id: {
            **{k: v for k, v in r.items() if k not in ("gpu_id", "host_id", "ts")},
            "ts": r["ts"].isoformat(),
        }
        for gpu_id, r in newest.items()
    }

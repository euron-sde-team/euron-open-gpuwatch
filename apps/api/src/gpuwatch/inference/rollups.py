"""Hourly inference rollups from per-interval samples (kept for months; raw rows for days)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from gpuwatch.inference import histograms
from gpuwatch.inference.models import InferenceEndpoint, InferenceRollup1h

_ROWS = text(
    """
    SELECT s.endpoint_id, date_trunc('hour', s.ts) AS bucket, s.interval_s, s.up, s.requests,
           s.prompt_tokens, s.generation_tokens, s.running, s.waiting, s.kv_cache_usage,
           s.ttft, s.itl, s.e2e
    FROM inference_samples s
    WHERE s.ts >= :start AND s.ts < :end AND s.endpoint_id = ANY(:endpoints)
    """
)


def _sum(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _wavg(pairs: list[tuple[float | None, float]]) -> float | None:
    present = [(v, w) for v, w in pairs if v is not None]
    weight = sum(w for _, w in present)
    return sum(v * w for v, w in present) / weight if weight else None


def _max(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return max(present) if present else None


async def recompute(
    conn: AsyncConnection, start: datetime, end: datetime, host_id: uuid.UUID | None
) -> None:
    stmt = select(InferenceEndpoint.id)
    if host_id is not None:
        stmt = stmt.where(InferenceEndpoint.host_id == host_id)
    endpoints = list((await conn.execute(stmt)).scalars().all())
    if not endpoints:
        return
    rows = (await conn.execute(_ROWS, {"start": start, "end": end, "endpoints": endpoints})).all()
    groups: dict[tuple[uuid.UUID, datetime], list[Any]] = defaultdict(list)
    for r in rows:
        groups[(r.endpoint_id, r.bucket)].append(r)
    if not groups:
        return
    await conn.execute(
        delete(InferenceRollup1h).where(
            InferenceRollup1h.endpoint_id.in_({k[0] for k in groups}),
            InferenceRollup1h.bucket.in_({k[1] for k in groups}),
        )
    )
    values = []
    for (endpoint_id, bucket), rs in groups.items():
        values.append(
            {
                "endpoint_id": endpoint_id,
                "bucket": bucket,
                "seconds": sum(r.interval_s for r in rs),
                "up_seconds": sum(r.interval_s for r in rs if r.up),
                "requests": _sum([r.requests for r in rs]),
                "prompt_tokens": _sum([r.prompt_tokens for r in rs]),
                "generation_tokens": _sum([r.generation_tokens for r in rs]),
                "running_avg": _wavg([(r.running, r.interval_s) for r in rs]),
                "waiting_avg": _wavg([(r.waiting, r.interval_s) for r in rs]),
                "waiting_max": _max([r.waiting for r in rs]),
                "kv_cache_avg": _wavg([(r.kv_cache_usage, r.interval_s) for r in rs]),
                "kv_cache_max": _max([r.kv_cache_usage for r in rs]),
                "ttft": histograms.merge(r.ttft for r in rs),
                "itl": histograms.merge(r.itl for r in rs),
                "e2e": histograms.merge(r.e2e for r in rs),
            }
        )
    await conn.execute(insert(InferenceRollup1h).values(values))

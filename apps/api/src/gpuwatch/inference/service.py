"""Inference statistics: throughput, latency percentiles and cost per token.

Cost per million tokens divides the bound GPUs' cost over the window (their monitored
seconds at the applied rate) by the tokens the server processed in it. With no rate, or
no GPU bound, it is null rather than a guess.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.core.errors import AppError, NotFoundError
from gpuwatch.costs.rates import applied_rates, seconds_cost
from gpuwatch.fleet.models import Gpu, Host
from gpuwatch.inference import histograms
from gpuwatch.inference.models import InferenceEndpoint
from gpuwatch.inference.schemas import EndpointOut, InferencePoint, InferenceSeries, InferenceStats

RAW_LIMIT = timedelta(days=2)


@dataclass
class _Row:
    ts: datetime
    seconds: float
    up_seconds: float
    requests: float | None
    prompt_tokens: float | None
    generation_tokens: float | None
    running: float | None
    waiting: float | None
    kv_cache: float | None
    ttft: dict[str, Any] | None
    itl: dict[str, Any] | None
    e2e: dict[str, Any] | None


_RAW = text(
    """
    SELECT ts, interval_s AS seconds, CASE WHEN up THEN interval_s ELSE 0 END AS up_seconds,
           requests, prompt_tokens, generation_tokens, running, waiting,
           kv_cache_usage AS kv_cache, ttft, itl, e2e
    FROM inference_samples WHERE endpoint_id = :ep AND ts >= :start AND ts < :end ORDER BY ts
    """
)
_HOURLY = text(
    """
    SELECT bucket AS ts, seconds, up_seconds, requests, prompt_tokens, generation_tokens,
           running_avg AS running, waiting_avg AS waiting, kv_cache_avg AS kv_cache, ttft, itl, e2e
    FROM inference_rollups_1h WHERE endpoint_id = :ep AND bucket >= :start AND bucket < :end
    ORDER BY bucket
    """
)
_GPU_TIME = text(
    """
    SELECT gpu_id, sum(seconds) AS seconds,
           sum(util_avg * seconds) FILTER (WHERE util_avg IS NOT NULL) AS util_weighted,
           sum(seconds) FILTER (WHERE util_avg IS NOT NULL) AS util_seconds
    FROM gpu_rollups_1m WHERE gpu_id = ANY(:gpus) AND bucket >= :start AND bucket < :end
    GROUP BY gpu_id
    """
)


async def _rows(session: AsyncSession, ep: uuid.UUID, start: datetime, end: datetime) -> list[_Row]:
    sql = _RAW if end - start <= RAW_LIMIT else _HOURLY
    result = await session.execute(sql, {"ep": ep, "start": start, "end": end})
    return [_Row(**dict(r)) for r in result.mappings().all()]


def _sum(values: Sequence[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _wavg(rows: Sequence[_Row], attr: str) -> float | None:
    pairs = [(getattr(r, attr), r.seconds) for r in rows if getattr(r, attr) is not None]
    weight = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / weight if weight else None


async def gpu_usage(
    session: AsyncSession, gpu_ids: list[uuid.UUID], start: datetime, end: datetime
) -> tuple[int | None, float | None]:
    """Cost of these GPUs over the window (None if any has no rate) and their average
    utilization."""
    if not gpu_ids:
        return None, None
    rows = (await session.execute(_GPU_TIME, {"gpus": gpu_ids, "start": start, "end": end})).all()
    rates = await applied_rates(session)
    cost: int | None = 0
    weighted = 0.0
    util_s = 0.0
    for gpu_id, seconds, util_weighted, util_seconds in rows:
        rate = rates.get(gpu_id)
        if rate is None or cost is None:
            cost = None
        else:
            cost += seconds_cost(float(seconds), rate.nusd_per_hour)
        weighted += float(util_weighted or 0)
        util_s += float(util_seconds or 0)
    if not rows:
        cost = None
    return cost, (weighted / util_s if util_s else None)


def stats(rows: Sequence[_Row], cost: int | None, util: float | None) -> InferenceStats:
    seconds = sum(r.seconds for r in rows)
    requests = _sum([r.requests for r in rows])
    prompt = _sum([r.prompt_tokens for r in rows])
    gen = _sum([r.generation_tokens for r in rows])
    ttft = histograms.merge(r.ttft for r in rows)
    itl = histograms.merge(r.itl for r in rows)
    e2e = histograms.merge(r.e2e for r in rows)
    tokens = (prompt or 0) + (gen or 0)
    return InferenceStats(
        seconds=seconds,
        requests=requests,
        requests_per_s=requests / seconds if requests is not None and seconds else None,
        prompt_tokens=prompt,
        generation_tokens=gen,
        generation_tokens_per_s=gen / seconds if gen is not None and seconds else None,
        ttft_p50_s=histograms.quantile(0.5, ttft),
        ttft_p95_s=histograms.quantile(0.95, ttft),
        itl_p50_s=histograms.quantile(0.5, itl),
        itl_p95_s=histograms.quantile(0.95, itl),
        e2e_p50_s=histograms.quantile(0.5, e2e),
        e2e_p95_s=histograms.quantile(0.95, e2e),
        running_avg=_wavg(rows, "running"),
        waiting_avg=_wavg(rows, "waiting"),
        kv_cache_avg=_wavg(rows, "kv_cache"),
        gpu_util_avg=util,
        gpu_cost_nusd=cost,
        nusd_per_million_tokens=round(cost * 1e6 / tokens) if cost is not None and tokens else None,
        nusd_per_request=round(cost / requests) if cost is not None and requests else None,
    )


def _gpu_ids(ep: InferenceEndpoint) -> list[uuid.UUID]:
    out = []
    for raw in ep.gpu_ids:
        try:
            out.append(uuid.UUID(str(raw)))
        except ValueError:
            continue
    return out


async def endpoint_stats(
    session: AsyncSession, ep: InferenceEndpoint, start: datetime, end: datetime
) -> InferenceStats:
    rows = await _rows(session, ep.id, start, end)
    cost, util = await gpu_usage(session, _gpu_ids(ep), start, end)
    return stats(rows, cost, util)


async def list_endpoints(session: AsyncSession) -> list[EndpointOut]:
    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(InferenceEndpoint, Host)
            .join(Host, Host.id == InferenceEndpoint.host_id)
            .order_by(Host.hostname, InferenceEndpoint.name)
        )
    ).all()
    gpus = {g.id: g for g in (await session.scalars(select(Gpu))).all()}
    out = []
    for ep, host in rows:
        ids = _gpu_ids(ep)
        out.append(
            EndpointOut(
                id=ep.id,
                host_id=host.id,
                host_name=host.display_name or host.hostname,
                name=ep.name,
                kind=ep.kind,
                url=ep.url,
                model=ep.model,
                gpu_ids=ids,
                gpu_labels=[f"{gpus[i].name} #{gpus[i].index}" for i in ids if i in gpus],
                up=ep.up
                and ep.last_seen_at is not None
                and now - ep.last_seen_at < timedelta(minutes=2),
                last_seen_at=ep.last_seen_at,
                stats_24h=await endpoint_stats(session, ep, now - timedelta(days=1), now),
            )
        )
    return out


async def series(
    session: AsyncSession, endpoint_id: uuid.UUID, start: datetime, end: datetime
) -> InferenceSeries:
    if end <= start:
        raise AppError("The end must be after the start", code="invalid_range")
    if end - start > timedelta(days=400):
        raise AppError("Choose a range of at most 400 days", code="range_too_long")
    ep = await session.get(InferenceEndpoint, endpoint_id)
    if ep is None:
        raise NotFoundError("Inference endpoint not found")
    rows = await _rows(session, ep.id, start, end)
    span = end - start
    bucket_s = 60 if span <= timedelta(hours=3) else 300 if span <= RAW_LIMIT else 3600
    groups: dict[datetime, list[_Row]] = defaultdict(list)
    for r in rows:
        epoch = int(r.ts.timestamp())
        groups[datetime.fromtimestamp(epoch - epoch % bucket_s, UTC)].append(r)
    points = []
    for ts in sorted(groups):
        g = groups[ts]
        st = stats(g, None, None)
        prompt = st.prompt_tokens
        points.append(
            InferencePoint(
                ts=ts,
                requests_per_s=st.requests_per_s,
                prompt_tokens_per_s=prompt / st.seconds
                if prompt is not None and st.seconds
                else None,
                generation_tokens_per_s=st.generation_tokens_per_s,
                ttft_p50_s=st.ttft_p50_s,
                ttft_p95_s=st.ttft_p95_s,
                itl_p50_s=st.itl_p50_s,
                e2e_p95_s=st.e2e_p95_s,
                running=st.running_avg,
                waiting=st.waiting_avg,
                kv_cache=st.kv_cache_avg,
            )
        )
    cost, util = await gpu_usage(session, _gpu_ids(ep), start, end)
    return InferenceSeries(
        endpoint_id=ep.id,
        start=start,
        end=end,
        bucket_s=bucket_s,
        summary=stats(rows, cost, util),
        points=points,
    )

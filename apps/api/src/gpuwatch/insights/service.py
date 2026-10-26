"""Running the insights engine and keeping its findings.

One evaluator at a time (advisory lock). For each finding the engine reports, the
unresolved row with the same fingerprint is updated (keeping its open, acknowledged or
dismissed status) or a new open row is created. Unresolved rows the engine no longer
reports are resolved: the condition cleared.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.audit.service import Actor, audit
from gpuwatch.core.container import Container
from gpuwatch.core.errors import NotFoundError
from gpuwatch.costs import service as cost_service
from gpuwatch.costs.models import GpuRate
from gpuwatch.costs.rates import applied_rates
from gpuwatch.fleet.models import Gpu, Host
from gpuwatch.inference import service as inference_service
from gpuwatch.inference.models import InferenceEndpoint
from gpuwatch.insights import engine
from gpuwatch.insights import settings as insight_settings
from gpuwatch.insights.models import AppSetting, Insight
from gpuwatch.insights.schemas import Explanation, InsightAction, InsightOut, InsightStatus
from gpuwatch.insights.settings import InsightSettings
from gpuwatch.observability import metrics

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}

_MINUTES = text(
    """
    SELECT gpu_id, bucket, seconds, util_avg, util_max, mem_used_max, mem_total, procs_max,
           busy_s, throttle_power_s, throttle_thermal_s, throttle_hw_s, ecc_max, xid_count
    FROM gpu_rollups_1m WHERE bucket >= :start AND bucket < :end ORDER BY gpu_id, bucket
    """
)
_HOLDERS = text(
    """
    SELECT gpu_id, workload, sum(idle_seconds) AS idle FROM workload_usage_1h
    WHERE bucket >= :start AND workload <> '' AND idle_seconds > 0
    GROUP BY gpu_id, workload ORDER BY gpu_id, sum(idle_seconds) DESC
    """
)
_ENDPOINT_MINUTES = text(
    """
    SELECT endpoint_id, date_trunc('minute', ts) AS bucket, sum(requests) AS requests,
           max(waiting) AS waiting, max(kv_cache_usage) AS kv_cache,
           sum(coalesce(prompt_tokens, 0) + coalesce(generation_tokens, 0)) AS tokens
    FROM inference_samples WHERE ts >= :start AND ts < :end
    GROUP BY endpoint_id, date_trunc('minute', ts) ORDER BY 1, 2
    """
)


async def evaluate(container: Container, now: datetime | None = None) -> int:
    """Run every rule over the fleet. Returns the number of findings reported."""
    now = now or datetime.now(UTC)
    async with container.db.sessionmaker() as session:
        if not await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtext('gpuwatch:insights'))")
        ):
            return 0
        cfg = await insight_settings.load(session)
        window = (now - timedelta(days=cfg.window_days), now)
        found = await _gpu_findings(session, cfg, window)
        found += await _endpoint_findings(session, cfg, now)
        await _store(session, found, now)
        await session.commit()
    return len(found)


async def _gpu_findings(
    session: AsyncSession, cfg: InsightSettings, window: tuple[datetime, datetime]
) -> list[engine.Finding]:
    gpus = (
        await session.execute(
            select(Gpu, Host)
            .join(Host, Host.id == Gpu.host_id)
            .where(Gpu.retired_at.is_(None), Host.revoked_at.is_(None))
        )
    ).all()
    rates = await applied_rates(session)
    minutes: dict[uuid.UUID, list[engine.Minute]] = defaultdict(list)
    for row in (await session.execute(_MINUTES, {"start": window[0], "end": window[1]})).all():
        minutes[row[0]].append(engine.Minute(*row[1:]))
    holders: dict[uuid.UUID, list[str]] = defaultdict(list)
    for gpu_id, workload, _idle in (await session.execute(_HOLDERS, {"start": window[0]})).all():
        holders[gpu_id].append(workload)
    model_rates = {
        r.gpu_model: r.nusd_per_hour
        for r in (await session.scalars(select(GpuRate).where(GpuRate.scope == "model"))).all()
        if r.gpu_model
    }
    memory: dict[str, float] = {}
    for gpu, _ in gpus:
        if gpu.memory_total_mib:
            memory[gpu.name] = max(memory.get(gpu.name, 0.0), gpu.memory_total_mib)
    catalog = [
        engine.CatalogEntry(model, memory[model], rate)
        for model, rate in model_rates.items()
        if model in memory
    ]
    found: list[engine.Finding] = []
    for gpu, host in gpus:
        rate = rates.get(gpu.id)
        ctx = engine.GpuContext(
            id=gpu.id,
            host_id=host.id,
            name=gpu.name,
            label=f"GPU {gpu.index} on {host.display_name or host.hostname}",
            memory_total_mib=gpu.memory_total_mib,
            nusd_per_hour=rate.nusd_per_hour if rate else None,
            idle_holders=tuple(holders.get(gpu.id, [])),
        )
        found += engine.evaluate_gpu(ctx, minutes.get(gpu.id, []), cfg, window, catalog)
    return found


async def _endpoint_findings(
    session: AsyncSession, cfg: InsightSettings, now: datetime
) -> list[engine.Finding]:
    window = (now - timedelta(days=1), now)
    endpoints = (await session.scalars(select(InferenceEndpoint))).all()
    if not endpoints:
        return []
    rows: dict[uuid.UUID, list[engine.EndpointMinute]] = defaultdict(list)
    tokens: dict[uuid.UUID, float] = defaultdict(float)
    for ep_id, bucket, requests, waiting, kv, tok in (
        await session.execute(_ENDPOINT_MINUTES, {"start": window[0], "end": window[1]})
    ).all():
        rows[ep_id].append(engine.EndpointMinute(bucket, requests, waiting, kv))
        tokens[ep_id] += float(tok or 0)
    found = []
    for ep in endpoints:
        gpu_ids = [uuid.UUID(str(g)) for g in ep.gpu_ids]
        cost, util = await inference_service.gpu_usage(session, gpu_ids, *window)
        ctx = engine.EndpointContext(
            ep.id, ep.host_id, ep.name, ep.kind, ep.model, util, tokens.get(ep.id, 0.0), cost
        )
        found += engine.inference_findings(ctx, rows.get(ep.id, []), cfg, window)
    return found


async def _store(session: AsyncSession, found: list[engine.Finding], now: datetime) -> None:
    open_rows = {
        r.fingerprint: r
        for r in (await session.scalars(select(Insight).where(Insight.status != "resolved"))).all()
    }
    reported = set()
    for f in found:
        reported.add(f.fingerprint)
        row = open_rows.get(f.fingerprint)
        if row is None:
            row = Insight(kind=f.kind, fingerprint=f.fingerprint, status="open", first_seen_at=now)
            session.add(row)
            metrics.INSIGHTS.labels(f.kind, "opened").inc()
        row.host_id, row.gpu_id, row.endpoint_id = f.host_id, f.gpu_id, f.endpoint_id
        row.severity, row.title, row.summary = f.severity, f.title, f.summary
        row.recommendation, row.evidence = f.recommendation, f.evidence
        row.window_start, row.window_end = f.window_start, f.window_end
        row.est_monthly_nusd = f.est_monthly_nusd
        row.last_seen_at = now
    for fingerprint, row in open_rows.items():
        if fingerprint not in reported:
            row.status = "resolved"
            row.resolved_at = now
            metrics.INSIGHTS.labels(row.kind, "resolved").inc()


async def _labels(
    session: AsyncSession,
) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, str], dict[uuid.UUID, str]]:
    hosts = {
        h.id: h.display_name or h.hostname for h in (await session.scalars(select(Host))).all()
    }
    gpus = {
        g.id: f"GPU {g.index} on {hosts.get(g.host_id, '?')}"
        for g in (await session.scalars(select(Gpu))).all()
    }
    endpoints = {e.id: e.name for e in (await session.scalars(select(InferenceEndpoint))).all()}
    return hosts, gpus, endpoints


def _out(
    r: Insight, hosts: dict[uuid.UUID, str], gpus: dict[uuid.UUID, str], eps: dict[uuid.UUID, str]
) -> InsightOut:
    return InsightOut(
        id=r.id,
        kind=r.kind,
        severity=r.severity,
        title=r.title,
        summary=r.summary,
        recommendation=r.recommendation,
        evidence=r.evidence,
        window_start=r.window_start,
        window_end=r.window_end,
        est_monthly_nusd=r.est_monthly_nusd,
        status=r.status,
        host_id=r.host_id,
        host_name=hosts.get(r.host_id) if r.host_id else None,
        gpu_id=r.gpu_id,
        gpu_label=gpus.get(r.gpu_id) if r.gpu_id else None,
        endpoint_id=r.endpoint_id,
        endpoint_name=eps.get(r.endpoint_id) if r.endpoint_id else None,
        first_seen_at=r.first_seen_at,
        last_seen_at=r.last_seen_at,
        resolved_at=r.resolved_at,
    )


def _rank(i: InsightOut) -> tuple[int, int, int]:
    return (
        0 if i.status == "open" else 1 if i.status == "acknowledged" else 2,
        -(i.est_monthly_nusd or 0),
        SEVERITY_RANK.get(i.severity, 3),
    )


async def list_insights(
    session: AsyncSession,
    status: list[InsightStatus] | None = None,
    gpu_id: uuid.UUID | None = None,
    limit: int = 200,
) -> list[InsightOut]:
    stmt = select(Insight)
    if status:
        stmt = stmt.where(Insight.status.in_(status))
    if gpu_id:
        stmt = stmt.where(Insight.gpu_id == gpu_id)
    rows = (await session.scalars(stmt.order_by(Insight.last_seen_at.desc()).limit(limit))).all()
    hosts, gpus, eps = await _labels(session)
    return sorted((_out(r, hosts, gpus, eps) for r in rows), key=_rank)


async def act(
    session: AsyncSession, insight_id: uuid.UUID, data: InsightAction, actor: Actor
) -> InsightOut:
    row = await session.get(Insight, insight_id)
    if row is None:
        raise NotFoundError("Insight not found")
    if row.status == "resolved":
        raise NotFoundError("This insight is resolved; it reopens by itself if the problem returns")
    row.status = {"acknowledge": "acknowledged", "dismiss": "dismissed", "reopen": "open"}[
        data.action
    ]
    row.acted_by = actor.id
    audit(session, actor, f"insight.{data.action}", "insight", row.id, kind=row.kind)
    await session.commit()
    hosts, gpus, eps = await _labels(session)
    return _out(row, hosts, gpus, eps)


async def get_settings(session: AsyncSession) -> InsightSettings:
    return await insight_settings.load(session)


async def put_settings(
    session: AsyncSession, data: InsightSettings, actor: Actor
) -> InsightSettings:
    row = await session.get(AppSetting, insight_settings.KEY)
    if row is None:
        session.add(
            AppSetting(key=insight_settings.KEY, value=data.model_dump(), updated_by=actor.id)
        )
    else:
        row.value = data.model_dump()
        row.updated_by = actor.id
    audit(session, actor, "settings.insights_updated", "settings", insight_settings.KEY)
    await session.commit()
    return data


async def explain(session: AsyncSession, gpu_id: uuid.UUID) -> Explanation:
    """The answer to "why is this GPU expensive or slow?" in a few sentences."""
    gpu = await session.get(Gpu, gpu_id)
    if gpu is None:
        raise NotFoundError("GPU not found")
    cfg = await insight_settings.load(session)
    now = datetime.now(UTC)
    start = now - timedelta(days=cfg.window_days)
    allocs, _ = await cost_service.allocations(
        session, start.replace(minute=0, second=0, microsecond=0), now
    )
    mine = [a for a in allocs if a.gpu.id == gpu_id]
    findings = await list_insights(session, status=["open", "acknowledged"], gpu_id=gpu_id)
    rates = await applied_rates(session)
    sentences: list[str] = []
    cost = idle = held = None
    if gpu_id in rates and mine:
        cost = sum(a.nusd for a in mine)
        idle = sum(a.nusd for a in mine if a.workload == "")
        held = sum(a.idle_nusd for a in mine if a.workload != "")
        by_workload: dict[str, int] = defaultdict(int)
        for a in mine:
            if a.workload:
                by_workload[a.workload] += a.nusd
        top = sorted(by_workload.items(), key=lambda kv: -kv[1])[:2]
        sentences.append(
            f"It cost {engine.usd(cost)} over the last {cfg.window_days} days"
            + (f", mostly {', '.join(f'{w} ({engine.usd(n)})' for w, n in top)}" if top else "")
            + "."
        )
        wasted = idle + held
        if cost and wasted:
            parts = [
                f"{engine.usd(n)} {what}"
                for n, what in (
                    (held, "with a model loaded and idle"),
                    (idle, "with nothing running"),
                )
                if n
            ]
            sentences.append(
                f"{wasted / cost:.0%} of that ({engine.usd(wasted)}) paid for time it did no work: "
                + " and ".join(parts)
                + "."
            )
    elif gpu_id not in rates:
        sentences.append("Set an hourly rate in Costs to see what this GPU costs and wastes.")
    for f in findings:
        if f.kind == "throttled":
            sentences.append(f.summary)
        elif f.kind in ("memory_pressure", "gpu_errors", "underused"):
            sentences.append(f.title + ".")
    if not findings and sentences:
        sentences.append("No problems found: utilization, memory, clocks and errors look healthy.")
    if not sentences:
        sentences.append("Not enough data yet. Findings appear after a few hours of monitoring.")
    slow = next((f for f in findings if f.kind == "throttled"), None)
    if (
        cost is not None
        and idle is not None
        and held is not None
        and cost
        and (idle + held) / cost >= 0.25
    ):
        headline = f"Expensive because it sits idle {(idle + held) / cost:.0%} of the time"
    elif slow:
        headline = slow.title
    elif findings:
        headline = findings[0].title
    else:
        headline = "Healthy and in use" if cost is not None else "No findings"
    return Explanation(
        gpu_id=gpu_id,
        window_days=cfg.window_days,
        headline=headline,
        sentences=sentences,
        cost_nusd=cost,
        idle_nusd=idle,
        held_idle_nusd=held,
        findings=findings,
    )

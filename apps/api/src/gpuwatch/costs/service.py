"""Rates, workload rules, cost summaries and report exports.

Exactness: per GPU-hour the cost is computed once from the GPU's monitored seconds and
rate, then split across that hour's workload rows by largest remainder. Every grouping
(by workload, team, host, GPU, model) sums the same split amounts, so the totals agree to
the nano-dollar and workloads plus idle always equal the GPUs' cost.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.audit.service import Actor, audit
from gpuwatch.core.container import Container
from gpuwatch.core.errors import AppError, ConflictError, NotFoundError
from gpuwatch.core.money import nusd_to_usd, usd_to_nusd
from gpuwatch.costs.attribution import UNATTRIBUTED
from gpuwatch.costs.models import IDLE_WORKLOAD, GpuRate, Report, WorkloadRule, WorkloadUsage1h
from gpuwatch.costs.rates import AppliedRate, applied_rates, seconds_cost
from gpuwatch.costs.schemas import (
    CostRow,
    CostSeries,
    CostSeriesPoint,
    CostSummary,
    GroupBy,
    RateIn,
    RateOut,
    RateUpdate,
    ReportIn,
    ReportOut,
    WorkloadRuleIn,
    WorkloadRuleOut,
)
from gpuwatch.fleet.models import Gpu, Host
from gpuwatch.telemetry.models import RollupDirty

IDLE_KEY = "__idle__"
IDLE_LABEL = "Idle (nothing running)"
MAX_RANGE = timedelta(days=400)

# ── rates ────────────────────────────────────────────────────────────────────


async def list_rates(session: AsyncSession) -> list[RateOut]:
    rates = (await session.scalars(select(GpuRate))).all()
    hosts = {h.id: h for h in (await session.scalars(select(Host))).all()}
    gpus = {g.id: g for g in (await session.scalars(select(Gpu))).all()}
    applied = await applied_rates(session)
    out = []
    for r in rates:
        covered = 0
        for gpu_id, rate in applied.items():
            g = gpus.get(gpu_id)
            if g is None or rate.scope != r.scope:
                continue
            if (
                (r.scope == "gpu" and gpu_id == r.gpu_id)
                or (r.scope == "host" and g.host_id == r.host_id)
                or (r.scope == "model" and g.name == r.gpu_model)
            ):
                covered += 1
        host = hosts.get(r.host_id) if r.host_id else None
        gpu = gpus.get(r.gpu_id) if r.gpu_id else None
        out.append(
            RateOut(
                id=r.id,
                scope=r.scope,
                gpu_model=r.gpu_model,
                host_id=r.host_id,
                host_name=(host.display_name or host.hostname) if host else None,
                gpu_id=r.gpu_id,
                gpu_label=f"{gpu.name} #{gpu.index}" if gpu else None,
                nusd_per_hour=r.nusd_per_hour,
                usd_per_hour=nusd_to_usd(r.nusd_per_hour),
                note=r.note,
                gpus_covered=covered,
                updated_at=r.updated_at,
            )
        )
    order = {"model": 0, "host": 1, "gpu": 2}
    return sorted(
        out, key=lambda r: (order[r.scope], r.gpu_model or r.host_name or r.gpu_label or "")
    )


async def create_rate(session: AsyncSession, data: RateIn, actor: Actor) -> RateOut:
    if data.scope == "host" and await session.get(Host, data.host_id) is None:
        raise NotFoundError("Host not found")
    if data.scope == "gpu" and await session.get(Gpu, data.gpu_id) is None:
        raise NotFoundError("GPU not found")
    target = {
        "model": GpuRate.gpu_model == data.gpu_model,
        "host": GpuRate.host_id == data.host_id,
        "gpu": GpuRate.gpu_id == data.gpu_id,
    }[data.scope]
    existing = await session.scalar(select(GpuRate.id).where(GpuRate.scope == data.scope, target))
    if existing:
        raise ConflictError("A rate for this already exists; edit it instead", code="rate_exists")
    rate = GpuRate(
        scope=data.scope,
        gpu_model=data.gpu_model if data.scope == "model" else None,
        host_id=data.host_id if data.scope == "host" else None,
        gpu_id=data.gpu_id if data.scope == "gpu" else None,
        nusd_per_hour=usd_to_nusd(data.usd_per_hour),
        note=data.note,
    )
    session.add(rate)
    await session.flush()
    audit(
        session,
        actor,
        "rate.created",
        "rate",
        rate.id,
        scope=data.scope,
        usd=str(data.usd_per_hour),
    )
    await session.commit()
    return next(r for r in await list_rates(session) if r.id == rate.id)


async def update_rate(
    session: AsyncSession, rate_id: uuid.UUID, data: RateUpdate, actor: Actor
) -> RateOut:
    rate = await session.get(GpuRate, rate_id)
    if rate is None:
        raise NotFoundError("Rate not found")
    if data.usd_per_hour is not None:
        rate.nusd_per_hour = usd_to_nusd(data.usd_per_hour)
    if "note" in data.model_fields_set:
        rate.note = data.note
    audit(session, actor, "rate.updated", "rate", rate.id)
    await session.commit()
    return next(r for r in await list_rates(session) if r.id == rate.id)


async def delete_rate(session: AsyncSession, rate_id: uuid.UUID, actor: Actor) -> None:
    rate = await session.get(GpuRate, rate_id)
    if rate is None:
        raise NotFoundError("Rate not found")
    await session.delete(rate)
    audit(session, actor, "rate.deleted", "rate", rate_id)
    await session.commit()


# ── workload rules ───────────────────────────────────────────────────────────


def rule_out(r: WorkloadRule) -> WorkloadRuleOut:
    return WorkloadRuleOut.model_validate(r, from_attributes=True)


async def list_rules(session: AsyncSession) -> list[WorkloadRuleOut]:
    rows = await session.scalars(
        select(WorkloadRule).order_by(WorkloadRule.priority, WorkloadRule.workload)
    )
    return [rule_out(r) for r in rows.all()]


async def create_rule(session: AsyncSession, data: WorkloadRuleIn, actor: Actor) -> WorkloadRuleOut:
    rule = WorkloadRule(**data.model_dump())
    session.add(rule)
    await session.flush()
    audit(session, actor, "workload_rule.created", "workload_rule", rule.id, workload=data.workload)
    await session.commit()
    return rule_out(rule)


async def update_rule(
    session: AsyncSession, rule_id: uuid.UUID, data: WorkloadRuleIn, actor: Actor
) -> WorkloadRuleOut:
    rule = await session.get(WorkloadRule, rule_id)
    if rule is None:
        raise NotFoundError("Workload rule not found")
    for field, value in data.model_dump().items():
        setattr(rule, field, value)
    audit(session, actor, "workload_rule.updated", "workload_rule", rule.id)
    await session.commit()
    return rule_out(rule)


async def delete_rule(session: AsyncSession, rule_id: uuid.UUID, actor: Actor) -> None:
    rule = await session.get(WorkloadRule, rule_id)
    if rule is None:
        raise NotFoundError("Workload rule not found")
    await session.delete(rule)
    audit(session, actor, "workload_rule.deleted", "workload_rule", rule_id)
    await session.commit()


async def reattribute(session: AsyncSession, container: Container, actor: Actor) -> int:
    """Apply the current rules to every hour that still has raw samples (rules otherwise
    apply from now on). Queues one rollup range per host; returns the number of hosts."""
    now = datetime.now(UTC)
    start = now - timedelta(days=container.settings.raw_retention_days)
    host_ids = (await session.scalars(select(Host.id))).all()
    for host_id in host_ids:
        session.add(RollupDirty(host_id=host_id, from_ts=start, to_ts=now))
    audit(session, actor, "workload_rule.reattributed", "workload_rule", None, hosts=len(host_ids))
    await session.commit()
    return len(host_ids)


# ── cost computation ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Gpu:
    id: uuid.UUID
    host_id: uuid.UUID
    name: str
    label: str
    host_name: str


@dataclass(frozen=True, slots=True)
class Allocation:
    gpu: _Gpu
    bucket: datetime
    workload: str
    team: str | None
    seconds: float
    nusd: int
    idle_nusd: int


def split(total: int, weights: list[float]) -> list[int]:
    """Integer amounts proportional to ``weights`` that add up to exactly ``total``
    (largest remainder; ties go to the earlier weight)."""
    weight_sum = sum(weights)
    if total == 0 or weight_sum <= 0:
        return [0] * len(weights)
    raw = [total * w / weight_sum for w in weights]
    floors = [int(x) for x in raw]
    remainder = total - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - floors[i]), i))
    for i in order[:remainder]:
        floors[i] += 1
    return floors


def _align(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    start = start.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    end = end.astimezone(UTC)
    if end.minute or end.second or end.microsecond:
        end = end.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    if end <= start:
        raise AppError("The end must be after the start", code="invalid_range")
    if end - start > MAX_RANGE:
        raise AppError("Choose a range of at most 400 days", code="range_too_long")
    return start, end


async def allocations(
    session: AsyncSession, start: datetime, end: datetime
) -> tuple[list[Allocation], float]:
    """Every priced (GPU, hour, workload) amount in the window, and unpriced GPU hours."""
    gpus = {
        g.id: _Gpu(
            g.id,
            g.host_id,
            g.name,
            f"{h.display_name or h.hostname} / GPU {g.index}",
            h.display_name or h.hostname,
        )
        for g, h in (
            await session.execute(select(Gpu, Host).join(Host, Host.id == Gpu.host_id))
        ).all()
    }
    rates: dict[uuid.UUID, AppliedRate] = await applied_rates(session)
    # Plain columns, not ORM entities: a month of usage is tens of thousands of rows.
    rows = (
        await session.execute(
            select(
                WorkloadUsage1h.gpu_id,
                WorkloadUsage1h.bucket,
                WorkloadUsage1h.workload,
                WorkloadUsage1h.team,
                WorkloadUsage1h.seconds,
                WorkloadUsage1h.idle_seconds,
            )
            .where(WorkloadUsage1h.bucket >= start, WorkloadUsage1h.bucket < end)
            .order_by(WorkloadUsage1h.gpu_id, WorkloadUsage1h.bucket, WorkloadUsage1h.workload)
        )
    ).all()
    by_cell: dict[tuple[uuid.UUID, datetime], list[Any]] = defaultdict(list)
    for r in rows:
        by_cell[(r.gpu_id, r.bucket)].append(r)
    out: list[Allocation] = []
    unpriced_s = 0.0
    for (gpu_id, bucket), cell in by_cell.items():
        gpu = gpus.get(gpu_id)
        if gpu is None:
            continue
        seconds = sum(r.seconds for r in cell)
        rate = rates.get(gpu_id)
        if rate is None:
            unpriced_s += seconds
            continue
        amounts = split(seconds_cost(seconds, rate.nusd_per_hour), [r.seconds for r in cell])
        for r, amount in zip(cell, amounts, strict=True):
            idle = (
                amount
                if r.workload == IDLE_WORKLOAD
                else (round(amount * r.idle_seconds / r.seconds) if r.seconds > 0 else 0)
            )
            out.append(Allocation(gpu, bucket, r.workload, r.team, r.seconds, amount, idle))
    return out, unpriced_s / 3600


def _keyer(group_by: GroupBy) -> Callable[[Allocation], tuple[str, str]]:
    def workload(a: Allocation) -> tuple[str, str]:
        if a.workload == IDLE_WORKLOAD:
            return IDLE_KEY, IDLE_LABEL
        return a.workload, a.workload

    def team(a: Allocation) -> tuple[str, str]:
        if a.workload == IDLE_WORKLOAD:
            return IDLE_KEY, IDLE_LABEL
        if a.workload == UNATTRIBUTED:
            return UNATTRIBUTED, "Unattributed (driver lists no processes)"
        return (a.team or "__none__"), (a.team or "No team")

    return {
        "workload": workload,
        "team": team,
        "host": lambda a: (str(a.gpu.host_id), a.gpu.host_name),
        "gpu": lambda a: (str(a.gpu.id), a.gpu.label),
        "model": lambda a: (a.gpu.name, a.gpu.name),
    }[group_by]


async def summary(
    session: AsyncSession, start: datetime, end: datetime, group_by: GroupBy
) -> CostSummary:
    start, end = _align(start, end)
    allocs, unpriced_h = await allocations(session, start, end)
    key = _keyer(group_by)
    groups: dict[str, list[float]] = {}
    labels: dict[str, str] = {}
    for a in allocs:
        k, label = key(a)
        g = groups.setdefault(k, [0, 0, 0.0])
        g[0] += a.nusd
        g[1] += a.idle_nusd
        g[2] += a.seconds / 3600
        labels[k] = label
    total = sum(a.nusd for a in allocs)
    rows = [
        CostRow(
            key=k,
            label=labels[k],
            nusd=int(v[0]),
            idle_nusd=int(v[1]),
            gpu_hours=round(v[2], 3),
            share=(v[0] / total) if total else 0.0,
        )
        for k, v in groups.items()
    ]
    rows.sort(key=lambda r: (-r.nusd, r.label))
    idle = sum(a.nusd for a in allocs if a.workload == IDLE_WORKLOAD)
    held = sum(a.idle_nusd for a in allocs if a.workload != IDLE_WORKLOAD)
    return CostSummary(
        start=start,
        end=end,
        group_by=group_by,
        total_nusd=total,
        idle_nusd=idle,
        held_idle_nusd=held,
        gpu_hours=round(sum(a.seconds for a in allocs) / 3600, 3),
        unpriced_gpu_hours=round(unpriced_h, 3),
        rows=rows,
    )


async def series(
    session: AsyncSession, start: datetime, end: datetime, group_by: GroupBy, top: int = 6
) -> CostSeries:
    start, end = _align(start, end)
    interval = "hour" if end - start <= timedelta(days=2) else "day"
    allocs, _ = await allocations(session, start, end)
    key = _keyer(group_by)
    totals: dict[str, int] = defaultdict(int)
    labels: dict[str, str] = {}
    for a in allocs:
        k, label = key(a)
        totals[k] += a.nusd
        labels[k] = label
    keep = [k for k, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:top]]
    if len(totals) > top:
        keep.append("__other__")
        labels["__other__"] = "Other"
    buckets: dict[datetime, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for a in allocs:
        b = a.bucket if interval == "hour" else a.bucket.replace(hour=0)
        k, _ = key(a)
        buckets[b][k if k in keep else "__other__"] += a.nusd
    points = []
    cursor = start if interval == "hour" else start.replace(hour=0)
    step = timedelta(hours=1) if interval == "hour" else timedelta(days=1)
    while cursor < end:
        points.append(
            CostSeriesPoint(bucket=cursor, values={k: buckets[cursor].get(k, 0) for k in keep})
        )
        cursor += step
    return CostSeries(
        start=start,
        end=end,
        group_by=group_by,
        interval=interval,
        keys=keep,
        labels={k: labels[k] for k in keep},
        points=points,
    )


# ── reports ──────────────────────────────────────────────────────────────────


def report_out(r: Report) -> ReportOut:
    return ReportOut(
        id=r.id,
        group_by=r.group_by,
        params={k: str(v) for k, v in r.params.items()},
        filename=r.filename,
        rows=r.rows,
        bytes=r.bytes,
        total_nusd=r.total_nusd,
        note=r.note,
        created_at=r.created_at,
    )


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_text(value: str) -> str:
    """A label as a spreadsheet will take it literally. Labels come from process names and
    hostnames that any user on a GPU host can choose; one starting with = or @ would run
    as a formula when the report is opened, so it gets a leading apostrophe."""
    return f"'{value}" if value.startswith(_FORMULA_START) else value


async def create_report(
    session: AsyncSession, container: Container, data: ReportIn, actor: Actor
) -> ReportOut:
    s = await summary(session, data.start, data.end, data.group_by)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([data.group_by, "cost_usd", "idle_cost_usd", "gpu_hours", "share_pct"])
    for row in s.rows:
        writer.writerow(
            [
                csv_text(row.label),
                f"{Decimal(row.nusd) / Decimal(10**9):.6f}",
                f"{Decimal(row.idle_nusd) / Decimal(10**9):.6f}",
                f"{row.gpu_hours:.3f}",
                f"{row.share * 100:.2f}",
            ]
        )
    writer.writerow(
        [
            "TOTAL",
            f"{Decimal(s.total_nusd) / Decimal(10**9):.6f}",
            "",
            f"{s.gpu_hours:.3f}",
            "100.00",
        ]
    )
    if s.unpriced_gpu_hours:
        writer.writerow(
            [f"(not priced: {s.unpriced_gpu_hours:.3f} GPU hours have no rate)", "", "", "", ""]
        )
    data_bytes = buf.getvalue().encode()
    report_id = uuid.uuid4()
    filename = f"gpuwatch-costs-by-{data.group_by}-{s.start:%Y%m%d}-{s.end:%Y%m%d}.csv"
    key = f"reports/{report_id}.csv"
    await container.storage.put(key, data_bytes, "text/csv")
    report = Report(
        id=report_id,
        group_by=data.group_by,
        params={"start": s.start.isoformat(), "end": s.end.isoformat()},
        object_key=key,
        filename=filename,
        rows=len(s.rows),
        bytes=len(data_bytes),
        total_nusd=s.total_nusd,
        note=data.note,
        created_by=actor.id,
    )
    session.add(report)
    audit(session, actor, "report.created", "report", report_id, group_by=data.group_by)
    await session.commit()
    return report_out(report)


async def list_reports(session: AsyncSession) -> list[ReportOut]:
    rows = await session.scalars(select(Report).order_by(Report.created_at.desc()).limit(100))
    return [report_out(r) for r in rows.all()]


async def report_file(
    session: AsyncSession, container: Container, report_id: uuid.UUID
) -> tuple[str, bytes]:
    report = await session.get(Report, report_id)
    if report is None:
        raise NotFoundError("Report not found")
    return report.filename, await container.storage.get(report.object_key)


async def total_since(session: AsyncSession, start: datetime, end: datetime) -> int:
    s = await summary(session, start, end, "host")
    return s.total_nusd


async def rate_count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(GpuRate)) or 0)

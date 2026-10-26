"""Who used the GPU: every monitored second of every GPU goes to exactly one bucket.

Per sample, the sample's interval is split across the processes on the GPU, weighted by
their SM share when the driver reports it, else by their VRAM, else equally. Processes map
to workloads through the workload rules. A sample with no process is idle (the GPU cost
money while nothing ran) unless the GPU was busy, which means the driver does not list
processes in this environment (``(unattributed)``, never silently idle).

Within a workload, the seconds spent below the idle threshold are also counted
(``idle_seconds``): the workload held the GPU (a model loaded) without using it.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from gpuwatch.costs.models import IDLE_WORKLOAD, WorkloadRule, WorkloadUsage1h
from gpuwatch.fleet.models import Host
from gpuwatch.insights import settings as insight_settings

UNATTRIBUTED = "(unattributed)"


@dataclass(frozen=True, slots=True)
class Rule:
    priority: int
    workload: str
    team: str | None
    process: re.Pattern[str] | None
    container_prefix: str | None
    username: str | None
    host_label: tuple[str, str] | None

    def matches(self, p: Proc, labels: dict[str, Any]) -> bool:
        if self.process is not None and not self.process.search(p.name):
            return False
        if self.container_prefix is not None and not (p.container_id or "").startswith(
            self.container_prefix
        ):
            return False
        if self.username is not None and p.username != self.username:
            return False
        return not (
            self.host_label is not None
            and str(labels.get(self.host_label[0], "")) != self.host_label[1]
        )


@dataclass(frozen=True, slots=True)
class Proc:
    pid: int
    name: str
    username: str | None
    container_id: str | None
    mem_used_mib: float | None
    sm_util: float | None


@dataclass(frozen=True, slots=True)
class Sample:
    gpu_id: uuid.UUID
    host_id: uuid.UUID
    ts: datetime
    interval_s: float
    util_gpu: float | None


def compile_rules(rows: Iterable[WorkloadRule]) -> list[Rule]:
    rules = []
    for r in sorted(rows, key=lambda r: (r.priority, r.workload)):
        if not r.enabled:
            continue
        label = None
        if r.host_label and "=" in r.host_label:
            k, v = r.host_label.split("=", 1)
            label = (k.strip(), v.strip())
        try:
            pattern = re.compile(r.process_pattern) if r.process_pattern else None
        except re.error:
            continue  # validated on write; a bad legacy pattern never breaks attribution
        rules.append(
            Rule(r.priority, r.workload, r.team, pattern, r.container_prefix, r.username, label)
        )
    return rules


def classify(p: Proc, rules: Sequence[Rule], labels: dict[str, Any]) -> tuple[str, str | None]:
    for rule in rules:
        if rule.matches(p, labels):
            return rule.workload, rule.team
    return p.name[:80], None


def _weights(procs: Sequence[Proc]) -> list[float]:
    sm = [p.sm_util or 0.0 for p in procs]
    if any(p.sm_util is not None for p in procs) and sum(sm) > 0:
        return sm
    mem = [p.mem_used_mib or 0.0 for p in procs]
    if sum(mem) > 0:
        return mem
    return [1.0] * len(procs)


HOUR_S = 3600.0
Usage = dict[tuple[uuid.UUID, datetime, str], list[Any]]  # -> [host_id, team, seconds, idle_s]


def attribute(
    samples: Iterable[Sample],
    procs: dict[tuple[uuid.UUID, datetime], list[Proc]],
    rules: Sequence[Rule],
    labels_by_host: dict[uuid.UUID, dict[str, Any]],
    idle_util_pct: float,
) -> Usage:
    """Seconds per (GPU, hour, workload). Invariant: per (GPU, hour), the seconds add up to
    the sum of the samples' intervals in that hour, capped at the hour itself (3600 s), so
    overlapping samples (two agents claiming one GPU during a rollout) never bill more
    than an hour of GPU per hour."""
    usage: Usage = {}

    def add(
        key: tuple[uuid.UUID, datetime, str],
        host: uuid.UUID,
        team: str | None,
        s: float,
        idle: float,
    ) -> None:
        row = usage.get(key)
        if row is None:
            usage[key] = [host, team, s, idle]
        else:
            row[2] += s
            row[3] += idle

    for smp in samples:
        hour = smp.ts.replace(minute=0, second=0, microsecond=0)
        running = procs.get((smp.gpu_id, smp.ts), [])
        if running:
            # Processes with no utilization reading (a card that does not report it) are
            # working as far as we know: never billed as held idle.
            idle = smp.util_gpu is not None and smp.util_gpu < idle_util_pct
        else:
            idle = smp.util_gpu is None or smp.util_gpu < idle_util_pct
        if not running:
            workload = IDLE_WORKLOAD if idle else UNATTRIBUTED
            add(
                (smp.gpu_id, hour, workload),
                smp.host_id,
                None,
                smp.interval_s,
                smp.interval_s if idle else 0.0,
            )
            continue
        weights = _weights(running)
        total = sum(weights)
        labels = labels_by_host.get(smp.host_id, {})
        for p, w in zip(running, weights, strict=True):
            share = smp.interval_s * w / total
            workload, team = classify(p, rules, labels)
            add((smp.gpu_id, hour, workload), smp.host_id, team, share, share if idle else 0.0)
    _cap_hours(usage)
    return usage


def _cap_hours(usage: Usage) -> None:
    per_hour: dict[tuple[uuid.UUID, datetime], float] = defaultdict(float)
    for (gpu, hour, _), row in usage.items():
        per_hour[(gpu, hour)] += row[2]
    for (gpu, hour, _), row in usage.items():
        total = per_hour[(gpu, hour)]
        if total > HOUR_S:
            row[2] *= HOUR_S / total
            row[3] *= HOUR_S / total


_SAMPLES = text(
    """
    SELECT gpu_id, host_id, ts, interval_s, util_gpu FROM gpu_samples
    WHERE ts >= :start AND ts < :end AND (CAST(:host AS uuid) IS NULL OR host_id = :host)
    """
)
_PROCS = text(
    """
    SELECT gpu_id, ts, pid, name, username, container_id, mem_used_mib, sm_util
    FROM process_samples
    WHERE ts >= :start AND ts < :end AND (CAST(:host AS uuid) IS NULL OR host_id = :host)
    """
)


async def recompute(
    conn: AsyncConnection,
    start: datetime,
    end: datetime,
    host_id: uuid.UUID | None,
) -> None:
    """Rebuild workload usage for whole hours [start, end) from raw samples.

    Hours whose raw samples were already dropped by retention keep their stored usage.
    """
    params = {"start": start, "end": end, "host": host_id}
    samples = [Sample(*row) for row in (await conn.execute(_SAMPLES, params)).all()]
    if not samples:
        return
    procs: dict[tuple[uuid.UUID, datetime], list[Proc]] = defaultdict(list)
    for gpu_id, ts, *rest in (await conn.execute(_PROCS, params)).all():
        procs[(gpu_id, ts)].append(Proc(*rest))
    # ORM rows through a session on the same connection (and transaction).
    async with AsyncSession(bind=conn) as orm:
        rules = compile_rules((await orm.scalars(select(WorkloadRule))).all())
    labels: dict[uuid.UUID, dict[str, Any]] = {
        row[0]: row[1] for row in (await conn.execute(select(Host.id, Host.labels))).all()
    }
    cfg = await insight_settings.load(conn)
    usage = attribute(samples, procs, rules, labels, cfg.idle_util_pct)
    gpu_ids = {s.gpu_id for s in samples}
    hours = {s.ts.replace(minute=0, second=0, microsecond=0) for s in samples}
    await conn.execute(
        delete(WorkloadUsage1h).where(
            WorkloadUsage1h.gpu_id.in_(gpu_ids), WorkloadUsage1h.bucket.in_(hours)
        )
    )
    rows = [
        {
            "gpu_id": gpu_id,
            "bucket": bucket,
            "workload": workload,
            "host_id": host,
            "team": team,
            "seconds": seconds,
            "idle_seconds": idle_s,
        }
        for (gpu_id, bucket, workload), (host, team, seconds, idle_s) in usage.items()
    ]
    for i in range(0, len(rows), 2_000):
        await conn.execute(insert(WorkloadUsage1h).values(rows[i : i + 2_000]))

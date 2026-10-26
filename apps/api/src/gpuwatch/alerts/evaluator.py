"""Alert evaluation: stateless over the stored samples, safe to run on any worker.

Threshold rules fire when every sample of a GPU over the rule's duration breaches the
threshold (a metric the GPU does not report never breaches), and resolve symmetrically,
when every sample over the same duration is clear: a GPU hovering at the threshold stays
one alert instead of firing and resolving every few minutes. Agent-offline and GPU-lost
rules read the fleet's last-seen times.

"Fires exactly once" is enforced by the database: a partial unique index allows one
unresolved event per (rule, target), and inserts use ON CONFLICT DO NOTHING. Notifications
are written to the outbox in the same transaction as the event change.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.alerts.models import AlertEvent, AlertRule, Channel, Notification
from gpuwatch.alerts.schemas import METRIC_LABELS
from gpuwatch.alerts.service import describe
from gpuwatch.core.container import Container
from gpuwatch.fleet.models import Gpu, Host
from gpuwatch.observability import metrics

log = logging.getLogger("gpuwatch.alerts")

_EXPR = {
    "util_gpu": "util_gpu",
    "util_mem": "util_mem",
    "mem_used_pct": "100.0 * mem_used_mib / nullif(mem_total_mib, 0)",
    "temp_c": "temp_c",
    "power_w": "power_w",
    "power_pct": "100.0 * power_w / nullif(power_limit_w, 0)",
    "fan_pct": "fan_pct",
}


@dataclass(frozen=True, slots=True)
class Target:
    key: str
    host_id: uuid.UUID
    gpu_id: uuid.UUID | None
    label: str


def _window_sql(metric: str, op: str) -> Any:
    expr = _EXPR[metric]
    cmp = ">" if op == "gt" else "<"
    # metric and op were validated against fixed maps; the threshold is a bound parameter.
    return text(
        f"""
        SELECT gpu_id, count(*) AS n,
               count(*) FILTER (WHERE ({expr}) {cmp} :threshold) AS n_breach,
               min(ts) AS first_ts,
               (array_agg(({expr}) ORDER BY ts DESC))[1] AS last_value,
               max(ts) AS last_ts
        FROM gpu_samples
        WHERE gpu_id = ANY(:gpus) AND ts >= :since
        GROUP BY gpu_id
        """
    )


def _in_scope(rule: AlertRule, gpu: Gpu, host: Host) -> bool:
    if rule.scope_gpu_id and gpu.id != rule.scope_gpu_id:
        return False
    if rule.scope_host_id and host.id != rule.scope_host_id:
        return False
    if rule.scope_label and "=" in rule.scope_label:
        k, v = rule.scope_label.split("=", 1)
        if str(host.labels.get(k.strip(), "")) != v.strip():
            return False
    return True


async def _open_events(session: AsyncSession, rule_id: uuid.UUID) -> dict[str, AlertEvent]:
    rows = await session.scalars(
        select(AlertEvent).where(AlertEvent.rule_id == rule_id, AlertEvent.resolved_at.is_(None))
    )
    return {e.target_key: e for e in rows.all()}


async def _notify(
    session: AsyncSession,
    rule: AlertRule,
    event_id: int,
    transition: str,
    payload: dict[str, Any],
    channels: dict[str, Channel],
) -> None:
    for cid in rule.channel_ids:
        channel = channels.get(str(cid))
        if channel is not None and channel.enabled:
            session.add(
                Notification(
                    event_id=event_id, channel_id=channel.id, transition=transition, payload=payload
                )
            )


def _payload(
    transition: str,
    rule: AlertRule,
    target: Target,
    message: str,
    value: float | None,
    started_at: datetime,
    dashboard_url: str,
    resolved_at: datetime | None = None,
) -> dict[str, Any]:
    link = f"{dashboard_url}/gpus/{target.gpu_id}" if target.gpu_id else f"{dashboard_url}/hosts"
    return {
        "type": f"alert.{transition}",
        "title": f"[{rule.severity.upper()}] {rule.name}"
        + (" resolved" if transition == "resolved" else ""),
        "message": message,
        "rule": {
            "id": str(rule.id),
            "name": rule.name,
            "kind": rule.kind,
            "condition": describe(rule),
        },
        "severity": rule.severity,
        "target": {
            "host_id": str(target.host_id),
            "gpu_id": str(target.gpu_id) if target.gpu_id else None,
            "label": target.label,
        },
        "value": value,
        "started_at": started_at.isoformat(),
        "resolved_at": resolved_at.isoformat() if resolved_at else None,
        "dashboard_url": link,
    }


async def _fire(
    session: AsyncSession,
    container: Container,
    rule: AlertRule,
    target: Target,
    message: str,
    value: float | None,
    now: datetime,
    channels: dict[str, Channel],
) -> None:
    event_id = await session.scalar(
        insert(AlertEvent)
        .values(
            rule_id=rule.id,
            target_key=target.key,
            host_id=target.host_id,
            gpu_id=target.gpu_id,
            severity=rule.severity,
            message=message,
            value=value,
            started_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=["rule_id", "target_key"], index_where=text("resolved_at IS NULL")
        )
        .returning(AlertEvent.id)
    )
    if event_id is None:
        return  # already firing (another evaluator got there first)
    metrics.ALERTS.labels(rule.kind, "fired").inc()
    log.warning("alert fired", extra={"rule": rule.name, "target": target.label, "value": value})
    payload = _payload("fired", rule, target, message, value, now, container.settings.dashboard_url)
    await _notify(session, rule, event_id, "fired", payload, channels)


async def _resolve(
    session: AsyncSession,
    container: Container,
    rule: AlertRule,
    event: AlertEvent,
    target: Target,
    value: float | None,
    now: datetime,
    channels: dict[str, Channel],
    why: str,
) -> None:
    result = await session.execute(
        update(AlertEvent)
        .where(AlertEvent.id == event.id, AlertEvent.resolved_at.is_(None))
        .values(resolved_at=now)
    )
    if not result.rowcount:  # type: ignore[attr-defined]
        return
    metrics.ALERTS.labels(rule.kind, "resolved").inc()
    if rule.notify_resolved:
        payload = _payload(
            "resolved",
            rule,
            target,
            f"{why} ({event.message})",
            value,
            event.started_at,
            container.settings.dashboard_url,
            now,
        )
        await _notify(session, rule, event.id, "resolved", payload, channels)


def _fmt(metric: str, value: float | None) -> str:
    label, unit = METRIC_LABELS[metric]
    return f"{label} {value:.1f}{unit}" if value is not None else f"{label} not reported"


async def evaluate(container: Container, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    s = container.settings
    async with container.db.sessionmaker() as session:
        if not await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtext('gpuwatch:alerts'))")
        ):
            return
        rules = (await session.scalars(select(AlertRule))).all()
        channels = {str(c.id): c for c in (await session.scalars(select(Channel))).all()}
        fleet = (
            await session.execute(
                select(Gpu, Host)
                .join(Host, Host.id == Gpu.host_id)
                .where(Host.revoked_at.is_(None))
            )
        ).all()
        hosts = {
            h.id: h
            for h in (await session.scalars(select(Host).where(Host.revoked_at.is_(None)))).all()
        }
        offline_after = timedelta(seconds=s.host_offline_after_s)
        for rule in rules:
            open_events = await _open_events(session, rule.id)
            if not rule.enabled:
                for event in open_events.values():
                    target = Target(
                        event.target_key,
                        event.host_id or uuid.uuid4(),
                        event.gpu_id,
                        event.target_key,
                    )
                    await _resolve(
                        session,
                        container,
                        rule,
                        event,
                        target,
                        None,
                        now,
                        channels,
                        "Rule disabled",
                    )
                continue
            if rule.kind == "agent_offline":
                await _agent_offline(
                    session, container, rule, hosts, open_events, now, offline_after, channels
                )
            elif rule.kind == "gpu_lost":
                await _gpu_lost(
                    session, container, rule, fleet, open_events, now, offline_after, channels
                )
            elif (
                rule.metric in _EXPR
                and rule.operator in ("gt", "lt")
                and rule.threshold is not None
            ):
                await _threshold(session, container, rule, fleet, open_events, now, channels)
        await session.commit()


async def _threshold(
    session: AsyncSession,
    container: Container,
    rule: AlertRule,
    fleet: Sequence[Any],
    open_events: dict[str, AlertEvent],
    now: datetime,
    channels: dict[str, Channel],
) -> None:
    assert rule.metric is not None
    assert rule.operator is not None
    assert rule.threshold is not None
    targets = {
        f"gpu:{g.id}": Target(
            f"gpu:{g.id}", h.id, g.id, f"GPU {g.index} on {h.display_name or h.hostname}"
        )
        for g, h in fleet
        if g.retired_at is None and _in_scope(rule, g, h)
    }
    window = max(rule.duration_s, 60)
    rows = (
        (
            await session.execute(
                _window_sql(rule.metric, rule.operator),
                {
                    "gpus": [t.gpu_id for t in targets.values()],
                    "since": now - timedelta(seconds=window),
                    "threshold": rule.threshold,
                },
            )
        )
        .mappings()
        .all()
    )
    stats = {f"gpu:{r['gpu_id']}": r for r in rows}
    # Samples arrive every few seconds; allow two intervals of slack at the window's start.
    slack = timedelta(seconds=15)
    op = ">" if rule.operator == "gt" else "<"
    for key, target in targets.items():
        st = stats.get(key)
        event = open_events.pop(key, None)
        if st is None:
            continue  # no recent data: offline rules cover it; keep any open event as is
        last = st["last_value"]
        breached = st["n"] > 0 and st["n_breach"] == st["n"]
        long_enough = (
            rule.duration_s == 0
            or st["first_ts"] <= now - timedelta(seconds=rule.duration_s) + slack
        )
        if event is None and breached and long_enough:
            message = (
                f"{_fmt(rule.metric, last)} on {target.label} "
                f"({op} {rule.threshold:g} for {rule.duration_s} s)"
            )
            await _fire(session, container, rule, target, message, last, now, channels)
        elif (
            event is not None
            and last is not None
            and st["n_breach"] == 0
            and (rule.duration_s == 0 or long_enough)
        ):
            await _resolve(
                session,
                container,
                rule,
                event,
                target,
                last,
                now,
                channels,
                f"Back to {_fmt(rule.metric, last)}",
            )
    # Open events whose GPU left the rule's scope (retired, rescoped, host revoked).
    for event in open_events.values():
        target = Target(
            event.target_key, event.host_id or uuid.uuid4(), event.gpu_id, event.target_key
        )
        await _resolve(
            session, container, rule, event, target, None, now, channels, "No longer in scope"
        )


async def _agent_offline(
    session: AsyncSession,
    container: Container,
    rule: AlertRule,
    hosts: dict[uuid.UUID, Host],
    open_events: dict[str, AlertEvent],
    now: datetime,
    offline_after: timedelta,
    channels: dict[str, Channel],
) -> None:
    for host in hosts.values():
        if rule.scope_host_id and host.id != rule.scope_host_id:
            continue
        key = f"host:{host.id}"
        name = host.display_name or host.hostname
        target = Target(key, host.id, None, name)
        event = open_events.pop(key, None)
        if host.last_seen_at is None:
            continue  # never reported: pending, not offline
        silent = now - host.last_seen_at
        if event is None and silent > offline_after:
            await _fire(
                session,
                container,
                rule,
                target,
                f"{name} has not reported for {int(silent.total_seconds())} s",
                None,
                now,
                channels,
            )
        elif event is not None and silent <= offline_after:
            await _resolve(
                session,
                container,
                rule,
                event,
                target,
                None,
                now,
                channels,
                f"{name} is reporting again",
            )
    for event in open_events.values():  # revoked or rescoped hosts
        target = Target(event.target_key, event.host_id or uuid.uuid4(), None, event.target_key)
        await _resolve(
            session, container, rule, event, target, None, now, channels, "Host no longer monitored"
        )


async def _gpu_lost(
    session: AsyncSession,
    container: Container,
    rule: AlertRule,
    fleet: Sequence[Any],
    open_events: dict[str, AlertEvent],
    now: datetime,
    offline_after: timedelta,
    channels: dict[str, Channel],
) -> None:
    for gpu, host in fleet:
        key = f"gpu:{gpu.id}"
        event = open_events.pop(key, None)
        if not _in_scope(rule, gpu, host):
            if event is not None:
                open_events[key] = event
            continue
        name = f"GPU {gpu.index} ({gpu.name}) on {host.display_name or host.hostname}"
        target = Target(key, host.id, gpu.id, name)
        host_online = host.last_seen_at is not None and now - host.last_seen_at <= offline_after
        grace = timedelta(seconds=max(30.0, 3 * (host.interval_s or 5.0)))
        lost = (
            gpu.retired_at is None
            and host_online
            and host.last_seen_at is not None
            and (gpu.last_seen_at is None or host.last_seen_at - gpu.last_seen_at > grace)
        )
        if event is None and lost:
            await _fire(
                session,
                container,
                rule,
                target,
                f"{name} stopped appearing in its host's reports",
                None,
                now,
                channels,
            )
        elif event is not None and (gpu.retired_at is not None or (host_online and not lost)):
            why = "GPU retired" if gpu.retired_at is not None else f"{name} is reporting again"
            await _resolve(session, container, rule, event, target, None, now, channels, why)
    for event in open_events.values():
        target = Target(
            event.target_key, event.host_id or uuid.uuid4(), event.gpu_id, event.target_key
        )
        await _resolve(
            session, container, rule, event, target, None, now, channels, "No longer in scope"
        )

"""Alert rules, channels, events and the notification history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.alerts.models import AlertEvent, AlertRule, Channel, Notification
from gpuwatch.alerts.schemas import (
    METRIC_LABELS,
    ChannelIn,
    ChannelOut,
    EventOut,
    NotificationOut,
    RuleIn,
    RuleOut,
)
from gpuwatch.alerts.urls import check_webhook_url
from gpuwatch.audit.service import Actor, audit
from gpuwatch.core.container import Container
from gpuwatch.core.errors import AppError, ConflictError, NotFoundError
from gpuwatch.fleet.models import Gpu, Host

# ── rules ────────────────────────────────────────────────────────────────────


def describe(rule: AlertRule) -> str:
    if rule.kind == "agent_offline":
        return "A host's agent stops reporting"
    if rule.kind == "gpu_lost":
        return "A GPU disappears from a host that still reports"
    label, unit = METRIC_LABELS.get(rule.metric or "", (rule.metric or "?", ""))
    op = "above" if rule.operator == "gt" else "below"
    duration = (
        f" for {rule.duration_s // 60} min"
        if rule.duration_s >= 60
        else (f" for {rule.duration_s} s" if rule.duration_s else "")
    )
    return f"{label} {op} {rule.threshold:g}{unit}{duration}"


def rule_out(rule: AlertRule, firing: int) -> RuleOut:
    return RuleOut(
        id=rule.id,
        name=rule.name,
        kind=rule.kind,
        metric=rule.metric,
        operator=rule.operator,
        threshold=rule.threshold,
        duration_s=rule.duration_s,
        scope_host_id=rule.scope_host_id,
        scope_gpu_id=rule.scope_gpu_id,
        scope_label=rule.scope_label,
        severity=rule.severity,
        channel_ids=[uuid.UUID(str(c)) for c in rule.channel_ids],
        notify_resolved=rule.notify_resolved,
        enabled=rule.enabled,
        description=describe(rule),
        firing=firing,
        created_at=rule.created_at,
    )


async def _firing_counts(session: AsyncSession) -> dict[uuid.UUID, int]:
    rows = await session.execute(
        select(AlertEvent.rule_id, func.count())
        .where(AlertEvent.resolved_at.is_(None))
        .group_by(AlertEvent.rule_id)
    )
    return {rule_id: int(n) for rule_id, n in rows.all()}


async def list_rules(session: AsyncSession) -> list[RuleOut]:
    counts = await _firing_counts(session)
    rules = (await session.scalars(select(AlertRule).order_by(AlertRule.created_at))).all()
    return [rule_out(r, counts.get(r.id, 0)) for r in rules]


async def _check_refs(session: AsyncSession, data: RuleIn) -> None:
    if data.scope_host_id and await session.get(Host, data.scope_host_id) is None:
        raise NotFoundError("The rule's host does not exist")
    if data.scope_gpu_id and await session.get(Gpu, data.scope_gpu_id) is None:
        raise NotFoundError("The rule's GPU does not exist")
    for channel_id in data.channel_ids:
        if await session.get(Channel, channel_id) is None:
            raise NotFoundError("One of the rule's channels does not exist")


async def create_rule(session: AsyncSession, data: RuleIn, actor: Actor) -> RuleOut:
    await _check_refs(session, data)
    values = data.model_dump()
    values["channel_ids"] = [str(c) for c in data.channel_ids]
    rule = AlertRule(**values)
    session.add(rule)
    await session.flush()
    audit(session, actor, "alert_rule.created", "alert_rule", rule.id, name=data.name)
    await session.commit()
    return rule_out(rule, 0)


async def update_rule(
    session: AsyncSession, rule_id: uuid.UUID, data: RuleIn, actor: Actor
) -> RuleOut:
    rule = await session.get(AlertRule, rule_id)
    if rule is None:
        raise NotFoundError("Alert rule not found")
    await _check_refs(session, data)
    for field, value in data.model_dump().items():
        setattr(rule, field, [str(c) for c in value] if field == "channel_ids" else value)
    audit(session, actor, "alert_rule.updated", "alert_rule", rule.id)
    await session.commit()
    return rule_out(rule, (await _firing_counts(session)).get(rule.id, 0))


async def delete_rule(session: AsyncSession, rule_id: uuid.UUID, actor: Actor) -> None:
    rule = await session.get(AlertRule, rule_id)
    if rule is None:
        raise NotFoundError("Alert rule not found")
    await session.delete(rule)
    audit(session, actor, "alert_rule.deleted", "alert_rule", rule_id, name=rule.name)
    await session.commit()


# ── events ───────────────────────────────────────────────────────────────────


async def list_events(
    session: AsyncSession, *, firing_only: bool, limit: int = 200
) -> list[EventOut]:
    stmt = (
        select(AlertEvent, AlertRule)
        .join(AlertRule, AlertRule.id == AlertEvent.rule_id)
        .order_by(AlertEvent.resolved_at.is_not(None), AlertEvent.started_at.desc())
        .limit(limit)
    )
    if firing_only:
        stmt = stmt.where(AlertEvent.resolved_at.is_(None))
    rows = (await session.execute(stmt)).all()
    hosts = {
        h.id: h.display_name or h.hostname for h in (await session.scalars(select(Host))).all()
    }
    gpus = {g.id: (g.index, g.host_id) for g in (await session.scalars(select(Gpu))).all()}
    ids = [e.id for e, _ in rows]
    counts: dict[int, tuple[int, int]] = {}
    if ids:
        for event_id, total, failed in (
            await session.execute(
                select(
                    Notification.event_id,
                    func.count(),
                    func.count().filter(Notification.failed_at.is_not(None)),
                )
                .where(Notification.event_id.in_(ids))
                .group_by(Notification.event_id)
            )
        ).all():
            if event_id is not None:
                counts[event_id] = (int(total), int(failed))
    out = []
    for e, r in rows:
        gpu = gpus.get(e.gpu_id) if e.gpu_id else None
        out.append(
            EventOut(
                id=e.id,
                rule_id=r.id,
                rule_name=r.name,
                kind=r.kind,
                severity=e.severity,
                message=e.message,
                value=e.value,
                host_id=e.host_id,
                host_name=hosts.get(e.host_id) if e.host_id else None,
                gpu_id=e.gpu_id,
                gpu_label=f"GPU {gpu[0]} on {hosts.get(gpu[1], '?')}" if gpu else None,
                started_at=e.started_at,
                resolved_at=e.resolved_at,
                notifications=counts.get(e.id, (0, 0))[0],
                notifications_failed=counts.get(e.id, (0, 0))[1],
            )
        )
    return out


async def firing_count(session: AsyncSession) -> int:
    stmt = select(func.count()).select_from(AlertEvent).where(AlertEvent.resolved_at.is_(None))
    return int(await session.scalar(stmt) or 0)


async def list_notifications(
    session: AsyncSession, event_id: int | None, limit: int = 100
) -> list[NotificationOut]:
    stmt = (
        select(Notification, Channel.name)
        .join(Channel, Channel.id == Notification.channel_id)
        .order_by(Notification.id.desc())
        .limit(limit)
    )
    if event_id is not None:
        stmt = stmt.where(Notification.event_id == event_id)
    return [
        NotificationOut(
            id=n.id,
            event_id=n.event_id,
            channel_id=n.channel_id,
            channel_name=name,
            transition=n.transition,
            attempts=n.attempts,
            delivered_at=n.delivered_at,
            failed_at=n.failed_at,
            next_attempt_at=n.next_attempt_at,
            last_error=n.last_error,
            created_at=n.created_at,
        )
        for n, name in (await session.execute(stmt)).all()
    ]


# ── channels ─────────────────────────────────────────────────────────────────


def masked_url(url: str) -> str:
    """Scheme and host only: chat webhook URLs (Slack, Teams, Discord) are credentials."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc.rpartition('@')[2]}/..."


def channel_out(c: Channel, *, reveal: bool = True) -> ChannelOut:
    return ChannelOut(
        id=c.id,
        name=c.name,
        kind=c.kind,
        emails=[str(e) for e in c.emails],
        url=c.url if reveal or c.url is None else masked_url(c.url),
        signed=c.sealed_secret is not None,
        enabled=c.enabled,
        last_delivery_at=c.last_delivery_at,
        last_error=c.last_error,
        created_at=c.created_at,
    )


async def list_channels(session: AsyncSession, actor: Actor) -> list[ChannelOut]:
    """Viewers and read-only keys see where webhooks go, not the full URL."""
    reveal = actor.role in ("admin", "owner")
    rows = await session.scalars(select(Channel).order_by(Channel.name))
    return [channel_out(c, reveal=reveal) for c in rows.all()]


async def _apply_channel(
    container: Container, channel: Channel, data: ChannelIn, *, creating: bool
) -> None:
    if data.kind == "webhook":
        assert data.url is not None
        await check_webhook_url(data.url, allow_private=container.settings.webhook_allow_private)
    channel.name = data.name
    channel.kind = data.kind
    channel.emails = list(data.emails) if data.kind == "email" else []
    channel.url = data.url if data.kind == "webhook" else None
    channel.enabled = data.enabled
    if data.kind == "email":
        channel.sealed_secret = None
    elif data.secret is not None or creating:
        channel.sealed_secret = (
            await container.sealer.seal(data.secret, f"channel:{channel.id}")
            if data.secret
            else None
        )


async def create_channel(
    session: AsyncSession, container: Container, data: ChannelIn, actor: Actor
) -> ChannelOut:
    if await session.scalar(select(Channel.id).where(Channel.name == data.name)):
        raise ConflictError("A channel with this name exists", code="channel_exists")
    channel = Channel(id=uuid.uuid4())
    await _apply_channel(container, channel, data, creating=True)
    session.add(channel)
    audit(session, actor, "channel.created", "channel", channel.id, kind=data.kind)
    await session.commit()
    return channel_out(channel)


async def update_channel(
    session: AsyncSession,
    container: Container,
    channel_id: uuid.UUID,
    data: ChannelIn,
    actor: Actor,
) -> ChannelOut:
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise NotFoundError("Channel not found")
    clash = await session.scalar(
        select(Channel.id).where(Channel.name == data.name, Channel.id != channel_id)
    )
    if clash:
        raise ConflictError("A channel with this name exists", code="channel_exists")
    await _apply_channel(container, channel, data, creating=False)
    audit(session, actor, "channel.updated", "channel", channel.id)
    await session.commit()
    return channel_out(channel)


async def delete_channel(session: AsyncSession, channel_id: uuid.UUID, actor: Actor) -> None:
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise NotFoundError("Channel not found")
    for rule in (await session.scalars(select(AlertRule))).all():
        if str(channel_id) in [str(c) for c in rule.channel_ids]:
            rule.channel_ids = [c for c in rule.channel_ids if str(c) != str(channel_id)]
    await session.delete(channel)
    audit(session, actor, "channel.deleted", "channel", channel_id)
    await session.commit()


async def test_channel(
    session: AsyncSession, channel_id: uuid.UUID, actor: Actor, dashboard_url: str
) -> None:
    """Queue a test notification; the worker delivers it like any other."""
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise NotFoundError("Channel not found")
    if not channel.enabled:
        raise AppError("Enable the channel to test it", code="channel_disabled")
    session.add(
        Notification(
            channel_id=channel.id,
            transition="test",
            payload={
                "type": "test",
                "title": "GPUWatch test notification",
                "message": f"{actor.email or 'Someone'} sent a test from the dashboard.",
                "dashboard_url": dashboard_url,
                "sent_at": datetime.now(UTC).isoformat(),
            },
        )
    )
    audit(session, actor, "channel.tested", "channel", channel.id)
    await session.commit()

"""Enrolment, hosts and GPUs.

Status is derived, never stored: a host is online while it reported within
``HOST_OFFLINE_AFTER_S``; a GPU is lost when its host still reports but the GPU stopped
appearing in the batches.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.audit.service import Actor, audit
from gpuwatch.core.config import Settings
from gpuwatch.core.container import Container
from gpuwatch.core.errors import AuthenticationError, NotFoundError
from gpuwatch.core.security import (
    ENROLMENT_PREFIX,
    HOST_TOKEN_PREFIX,
    constant_time_equals,
    generate_api_key,
    hash_key_secret,
    parse_api_key,
)
from gpuwatch.costs.rates import applied_rates
from gpuwatch.fleet.models import EnrolmentToken, Gpu, Host
from gpuwatch.fleet.schemas import (
    EnrolmentTokenCreated,
    EnrolmentTokenIn,
    EnrolmentTokenOut,
    GpuOut,
    GpuStatus,
    GpuUpdate,
    HostOut,
    HostStatus,
    HostUpdate,
)
from gpuwatch.ingest.schemas import EnrolIn, Enrolled
from gpuwatch.observability import metrics
from gpuwatch.telemetry import live

# ── enrolment tokens ─────────────────────────────────────────────────────────


def _token_usable(t: EnrolmentToken, now: datetime) -> bool:
    return (
        t.revoked_at is None
        and (t.expires_at is None or t.expires_at > now)
        and (t.max_uses is None or t.uses < t.max_uses)
    )


def token_out(t: EnrolmentToken) -> EnrolmentTokenOut:
    return EnrolmentTokenOut(
        id=t.id,
        name=t.name,
        display=f"{ENROLMENT_PREFIX}_{t.prefix}_****",
        labels=t.labels,
        simulated=t.simulated,
        expires_at=t.expires_at,
        max_uses=t.max_uses,
        uses=t.uses,
        revoked_at=t.revoked_at,
        created_at=t.created_at,
        usable=_token_usable(t, datetime.now(UTC)),
    )


async def list_tokens(session: AsyncSession) -> list[EnrolmentTokenOut]:
    rows = await session.scalars(select(EnrolmentToken).order_by(EnrolmentToken.created_at.desc()))
    return [token_out(t) for t in rows.all()]


async def create_token(
    session: AsyncSession,
    data: EnrolmentTokenIn,
    pepper: str,
    actor: Actor | None,
    *,
    simulated: bool = False,
) -> EnrolmentTokenCreated:
    generated = generate_api_key(pepper, ENROLMENT_PREFIX)
    token = EnrolmentToken(
        name=data.name,
        prefix=generated.prefix,
        secret_hash=generated.secret_hash,
        labels=data.labels,
        simulated=simulated,
        expires_at=(
            datetime.now(UTC) + timedelta(days=data.expires_in_days)
            if data.expires_in_days
            else None
        ),
        max_uses=data.max_uses,
        created_by=actor.id if actor else None,
    )
    session.add(token)
    await session.flush()
    await session.refresh(token)
    if actor:
        audit(
            session, actor, "enrolment_token.created", "enrolment_token", token.id, name=data.name
        )
    await session.commit()
    return EnrolmentTokenCreated(**token_out(token).model_dump(), token=generated.plaintext)


async def revoke_token(
    session: AsyncSession, token_id: uuid.UUID, actor: Actor
) -> EnrolmentTokenOut:
    token = await session.get(EnrolmentToken, token_id)
    if token is None:
        raise NotFoundError("Enrolment token not found")
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        audit(session, actor, "enrolment_token.revoked", "enrolment_token", token.id)
        await session.commit()
    return token_out(token)


# ── enrolment ────────────────────────────────────────────────────────────────

_ENROLMENT_REFUSED = "This enrolment token is not valid. Create a new one in Hosts, Add a host"


async def enrol(session: AsyncSession, data: EnrolIn, container: Container) -> Enrolled:
    """Exchange an enrolment token for a host token. Re-enrolling the same machine keeps
    its host (and history) and rotates the token.

    A revoked machine stays revoked: its agent still holds the enrolment token it started
    with, so re-enrolment needs a token created after the revocation (an admin's decision
    to bring it back), not just any token that is still valid."""
    pepper = container.settings.api_key_pepper
    parsed = parse_api_key(data.token, ENROLMENT_PREFIX)
    if parsed is None:
        metrics.ENROLMENTS.labels("invalid").inc()
        raise AuthenticationError(_ENROLMENT_REFUSED, code="invalid_enrolment_token")
    prefix, secret = parsed
    now = datetime.now(UTC)
    token = await session.scalar(
        select(EnrolmentToken).where(EnrolmentToken.prefix == prefix).with_for_update()
    )
    if (
        token is None
        or not constant_time_equals(token.secret_hash, hash_key_secret(secret, pepper))
        or not _token_usable(token, now)
    ):
        metrics.ENROLMENTS.labels("refused").inc()
        raise AuthenticationError(_ENROLMENT_REFUSED, code="invalid_enrolment_token")
    host = await session.scalar(select(Host).where(Host.machine_id == data.machine_id))
    if host is not None and host.revoked_at is not None and token.created_at <= host.revoked_at:
        metrics.ENROLMENTS.labels("refused").inc()
        raise AuthenticationError(
            "This machine was revoked. To bring it back, create a new enrolment token in "
            "Hosts, Add a host, and restart the agent with it.",
            code="host_revoked",
        )
    generated = generate_api_key(pepper, HOST_TOKEN_PREFIX)
    if host is None:
        host = Host(
            machine_id=data.machine_id,
            hostname=data.hostname,
            labels={**token.labels, **data.labels},
            token_prefix=generated.prefix,
            token_hash=generated.secret_hash,
            enrolled_with=token.id,
            simulated=token.simulated,
        )
        session.add(host)
    else:
        host.hostname = data.hostname
        host.labels = {**host.labels, **token.labels, **data.labels}
        host.token_prefix = generated.prefix
        host.token_hash = generated.secret_hash
        host.enrolled_with = token.id
        host.simulated = token.simulated
        host.revoked_at = None
    token.uses += 1
    await session.flush()
    audit(
        session,
        Actor(None, None, "agent", None),
        "host.enrolled",
        "host",
        host.id,
        hostname=data.hostname,
        token=token.name,
    )
    await session.commit()
    await container.config_cache.invalidate()
    metrics.ENROLMENTS.labels("ok").inc()
    return Enrolled(host_id=host.id, host_token=generated.plaintext, simulated=host.simulated)


# ── hosts ────────────────────────────────────────────────────────────────────


def host_status(host: Host, settings: Settings, now: datetime) -> HostStatus:
    if host.revoked_at is not None:
        return "revoked"
    if host.last_seen_at is None:
        return "pending"
    if now - host.last_seen_at > timedelta(seconds=settings.host_offline_after_s):
        return "disconnected"
    return "online"


def host_out(host: Host, gpu_count: int, settings: Settings, now: datetime) -> HostOut:
    return HostOut(
        id=host.id,
        name=host.display_name or host.hostname,
        hostname=host.hostname,
        machine_id=host.machine_id,
        labels=host.labels,
        status=host_status(host, settings, now),
        agent_status="degraded" if host.agent_status == "degraded" else "ok",
        problems=host.problems,
        simulated=host.simulated,
        agent_version=host.agent_version,
        collector=host.collector,
        os=host.os,
        kernel=host.kernel,
        driver_version=host.driver_version,
        cuda_version=host.cuda_version,
        interval_s=host.interval_s,
        gpu_count=gpu_count,
        first_seen_at=host.first_seen_at,
        last_seen_at=host.last_seen_at,
        created_at=host.created_at,
    )


async def _gpu_counts(session: AsyncSession) -> dict[uuid.UUID, int]:
    rows = await session.execute(
        select(Gpu.host_id, func.count()).where(Gpu.retired_at.is_(None)).group_by(Gpu.host_id)
    )
    return {host_id: int(n) for host_id, n in rows.all()}


async def list_hosts(session: AsyncSession, settings: Settings) -> list[HostOut]:
    now = datetime.now(UTC)
    counts = await _gpu_counts(session)
    hosts = (await session.scalars(select(Host).order_by(Host.hostname))).all()
    return [host_out(h, counts.get(h.id, 0), settings, now) for h in hosts]


async def get_host(session: AsyncSession, host_id: uuid.UUID, settings: Settings) -> HostOut:
    host = await session.get(Host, host_id)
    if host is None:
        raise NotFoundError("Host not found")
    counts = await _gpu_counts(session)
    return host_out(host, counts.get(host.id, 0), settings, datetime.now(UTC))


async def update_host(
    session: AsyncSession, host_id: uuid.UUID, data: HostUpdate, container: Container, actor: Actor
) -> HostOut:
    host = await session.get(Host, host_id)
    if host is None:
        raise NotFoundError("Host not found")
    changes = data.model_dump(exclude_unset=True)
    if "display_name" in changes:
        host.display_name = changes["display_name"] or None
    if "labels" in changes and changes["labels"] is not None:
        host.labels = changes["labels"]
    audit(session, actor, "host.updated", "host", host.id, fields=sorted(changes))
    await session.commit()
    await container.config_cache.invalidate()
    return await get_host(session, host_id, container.settings)


async def revoke_host(
    session: AsyncSession, host_id: uuid.UUID, container: Container, actor: Actor
) -> HostOut:
    """The host's token stops working at once; history stays. Re-enrol to bring it back."""
    host = await session.get(Host, host_id)
    if host is None:
        raise NotFoundError("Host not found")
    if host.revoked_at is None:
        host.revoked_at = datetime.now(UTC)
        audit(session, actor, "host.revoked", "host", host.id, hostname=host.hostname)
        await session.commit()
        await container.config_cache.invalidate()
    return await get_host(session, host_id, container.settings)


# ── GPUs ─────────────────────────────────────────────────────────────────────


def gpu_status(gpu: Gpu, host: Host, settings: Settings, now: datetime) -> GpuStatus:
    if gpu.retired_at is not None:
        return "retired"
    if host_status(host, settings, now) != "online":
        return "offline"
    grace = timedelta(seconds=max(30.0, 3 * (host.interval_s or 5.0)))
    if gpu.last_seen_at is None or (
        host.last_seen_at is not None and host.last_seen_at - gpu.last_seen_at > grace
    ):
        return "lost"
    return "ok"


async def list_gpus(
    session: AsyncSession,
    container: Container,
    *,
    host_id: uuid.UUID | None = None,
    include_retired: bool = False,
) -> list[GpuOut]:
    stmt = select(Gpu, Host).join(Host, Host.id == Gpu.host_id).order_by(Host.hostname, Gpu.index)
    if host_id is not None:
        stmt = stmt.where(Gpu.host_id == host_id)
    elif not include_retired:
        # A revoked host's GPUs stay on its own page and in history, not in the fleet.
        stmt = stmt.where(Host.revoked_at.is_(None))
    if not include_retired:
        stmt = stmt.where(Gpu.retired_at.is_(None))
    rows = (await session.execute(stmt)).all()
    rates = await applied_rates(session)
    latest = await live.latest(container, [g.id for g, _ in rows])
    now = datetime.now(UTC)
    out = []
    for gpu, host in rows:
        rate = rates.get(gpu.id)
        status = gpu_status(gpu, host, container.settings, now)
        out.append(
            GpuOut(
                id=gpu.id,
                host_id=host.id,
                host_name=host.display_name or host.hostname,
                host_simulated=host.simulated,
                uuid=gpu.uuid,
                index=gpu.index,
                name=gpu.name,
                memory_total_mib=gpu.memory_total_mib,
                power_limit_w=gpu.power_limit_w,
                pci_bus_id=gpu.pci_bus_id,
                mig_mode=gpu.mig_mode,
                status=status,
                first_seen_at=gpu.first_seen_at,
                last_seen_at=gpu.last_seen_at,
                retired_at=gpu.retired_at,
                nusd_per_hour=rate.nusd_per_hour if rate else None,
                rate_scope=rate.scope if rate else None,
                live=latest.get(gpu.id) if status in ("ok", "lost") else None,
            )
        )
    return out


async def get_gpu(session: AsyncSession, gpu_id: uuid.UUID, container: Container) -> GpuOut:
    gpu = await session.get(Gpu, gpu_id)
    if gpu is None:
        raise NotFoundError("GPU not found")
    for g in await list_gpus(session, container, host_id=gpu.host_id, include_retired=True):
        if g.id == gpu_id:
            return g
    raise NotFoundError("GPU not found")


async def update_gpu(
    session: AsyncSession, gpu_id: uuid.UUID, data: GpuUpdate, container: Container, actor: Actor
) -> GpuOut:
    gpu = await session.get(Gpu, gpu_id)
    if gpu is None:
        raise NotFoundError("GPU not found")
    gpu.retired_at = datetime.now(UTC) if data.retired else None
    audit(session, actor, "gpu.retired" if data.retired else "gpu.restored", "gpu", gpu.id)
    await session.commit()
    return await get_gpu(session, gpu_id, container)


async def touch_retired_back(session: AsyncSession, gpu_ids: list[uuid.UUID]) -> None:
    """A retired GPU that reports again is back in service."""
    if gpu_ids:
        await session.execute(
            update(Gpu)
            .where(Gpu.id.in_(gpu_ids), Gpu.retired_at.is_not(None))
            .values(retired_at=None)
        )

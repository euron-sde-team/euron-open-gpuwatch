"""Agent authentication (host tokens) and per-host ingest rate limits.

The host row is read through the config cache (5 s TTL, invalidated cluster-wide on
enrolment and revocation), so the hot path does not wait on Postgres for every batch.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from redis.exceptions import RedisError
from sqlalchemy import select

from gpuwatch.core.container import Container
from gpuwatch.core.deps import ContainerDep
from gpuwatch.core.errors import AuthenticationError, RateLimitedError
from gpuwatch.core.security import (
    HOST_TOKEN_PREFIX,
    constant_time_equals,
    hash_key_secret,
    parse_api_key,
)
from gpuwatch.fleet.models import Host
from gpuwatch.observability import metrics


@dataclass(frozen=True, slots=True)
class AgentHost:
    id: uuid.UUID
    hostname: str
    simulated: bool
    token_hash: str
    revoked: bool


async def _load(container: Container, prefix: str) -> AgentHost | None:
    async with container.db.sessionmaker() as session:
        host = await session.scalar(select(Host).where(Host.token_prefix == prefix))
        if host is None:
            return None
        return AgentHost(
            host.id, host.hostname, host.simulated, host.token_hash, host.revoked_at is not None
        )


async def agent_host(request: Request, container: ContainerDep) -> AgentHost:
    header = request.headers.get("authorization", "")
    raw = header[7:].strip() if header.lower().startswith("bearer ") else ""
    parsed = parse_api_key(raw, HOST_TOKEN_PREFIX) if raw else None
    if parsed is None:
        raise AuthenticationError(
            "Send the host token from enrolment as 'Authorization: Bearer gwh_...'",
            code="missing_host_token",
        )
    prefix, secret = parsed
    host = await container.config_cache.get(f"host:{prefix}", lambda: _load(container, prefix))
    if host is None or not constant_time_equals(
        host.token_hash, hash_key_secret(secret, container.settings.api_key_pepper)
    ):
        # The agent re-enrols when it sees this code (its token was rotated or revoked).
        raise AuthenticationError("Unknown host token", code="invalid_host_token")
    if host.revoked:
        raise AuthenticationError(
            "This host was revoked in the dashboard. Enrol it again to resume",
            code="host_revoked",
        )
    limit = container.settings.ingest_rpm_per_host
    try:
        decision = await container.kv.hit(f"ingest:{host.id}", limit)
    except (RedisError, OSError):
        metrics.DEPENDENCY_ERRORS.labels("redis", "rate_limit").inc()
        decision = None
    if decision is not None and not decision.allowed:
        metrics.INGEST_BATCHES.labels("rate_limited").inc()
        raise RateLimitedError(
            f"More than {limit} batches a minute from this host",
            details={"limit_rpm": limit, "retry_after_s": decision.retry_after_s},
            headers={"retry-after": str(decision.retry_after_s)},
        )
    return host


AgentHostDep = Annotated[AgentHost, Depends(agent_host)]

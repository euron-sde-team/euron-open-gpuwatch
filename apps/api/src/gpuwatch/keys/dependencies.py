"""API key authentication and per-key rate limits for the read-only REST API.

Lookups go through the config cache (5 s TTL, cluster-wide invalidation), so the hot path
never waits on Postgres; ``last_used_at`` is touched at most once a minute per key.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis.exceptions import RedisError
from sqlalchemy import select, update

from gpuwatch.core.container import Container
from gpuwatch.core.errors import AuthenticationError, RateLimitedError
from gpuwatch.core.security import constant_time_equals, hash_key_secret, parse_api_key
from gpuwatch.keys.models import ApiKey
from gpuwatch.observability import metrics

log = logging.getLogger("gpuwatch.keys")
_TOUCH_EVERY = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class KeyContext:
    id: uuid.UUID
    name: str
    rpm_limit: int


@dataclass(frozen=True, slots=True)
class _KeyRow:
    id: uuid.UUID
    name: str
    secret_hash: str
    rpm_limit: int | None
    expires_at: datetime | None
    revoked: bool
    last_used_at: datetime | None


async def _load(container: Container, prefix: str) -> _KeyRow | None:
    async with container.db.sessionmaker() as session:
        key = await session.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
        if key is None:
            return None
        return _KeyRow(
            key.id,
            key.name,
            key.secret_hash,
            key.rpm_limit,
            key.expires_at,
            key.revoked_at is not None,
            key.last_used_at,
        )


async def authenticate_key(raw: str, container: Container) -> KeyContext:
    settings = container.settings
    parsed = parse_api_key(raw)
    if parsed is None:
        raise AuthenticationError(
            "That is not a GPUWatch API key (gwk_...)", code="invalid_api_key"
        )
    prefix, secret = parsed
    row = await container.config_cache.get(f"key:{prefix}", lambda: _load(container, prefix))
    now = datetime.now(UTC)
    if row is None or not constant_time_equals(
        row.secret_hash, hash_key_secret(secret, settings.api_key_pepper)
    ):
        raise AuthenticationError("Unknown API key", code="invalid_api_key")
    if row.revoked:
        raise AuthenticationError("This API key was revoked", code="revoked_api_key")
    if row.expires_at and row.expires_at <= now:
        raise AuthenticationError("This API key has expired", code="expired_api_key")
    limit = row.rpm_limit or settings.default_rpm_limit
    try:
        decision = await container.kv.hit(f"key:{row.id}", limit)
    except (RedisError, OSError):
        metrics.DEPENDENCY_ERRORS.labels("redis", "rate_limit").inc()
        decision = None  # rate limits are protective; reads keep working
    if decision is not None and not decision.allowed:
        raise RateLimitedError(
            f"Rate limit of {limit} requests per minute reached for this key",
            details={"limit_rpm": limit, "retry_after_s": decision.retry_after_s},
            headers={"retry-after": str(decision.retry_after_s)},
        )
    # The row is cached for a few seconds, so its last_used_at lags; remember this
    # process's own last write too, or every request in that window would write again.
    touched = container.key_touched.get(row.id)
    last = max(filter(None, (row.last_used_at, touched)), default=None)
    if last is None or now - last > _TOUCH_EVERY:
        container.key_touched[row.id] = now
        try:
            async with container.db.sessionmaker() as session:
                await session.execute(
                    update(ApiKey).where(ApiKey.id == row.id).values(last_used_at=now)
                )
                await session.commit()
        except Exception:  # a failed bookkeeping write must not fail the request
            log.warning("could not record key usage", exc_info=True)
    return KeyContext(row.id, row.name, limit)

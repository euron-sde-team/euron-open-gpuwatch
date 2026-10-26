"""Health, readiness, metrics and deployment info."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from typing import Any

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from gpuwatch import __version__
from gpuwatch.auth.dependencies import Viewer
from gpuwatch.core.deps import ContainerDep, SessionDep
from gpuwatch.core.errors import AuthenticationError
from gpuwatch.core.schemas import ApiModel
from gpuwatch.core.security import constant_time_equals
from gpuwatch.keys import service as key_service
from gpuwatch.observability import fleet

router = APIRouter(tags=["system"])


@router.get("/healthz", summary="Liveness")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health", summary="Liveness (alias of /healthz)")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


async def _probe(name: str, coro: Awaitable[Any]) -> tuple[str, dict[str, Any]]:
    t0 = time.perf_counter()
    try:
        await asyncio.wait_for(coro, timeout=2)
        return name, {"ok": True, "ms": round((time.perf_counter() - t0) * 1000, 1)}
    except Exception as exc:
        return name, {"ok": False, "error": type(exc).__name__}


@router.get("/readyz", summary="Readiness: Postgres reachable (Redis too, when configured)")
async def readyz(container: ContainerDep, response: Response) -> dict[str, Any]:
    async def pg() -> None:
        async with container.db.engine.connect() as conn:
            await conn.execute(text("select 1"))

    probes = [_probe("postgres", pg())]
    if container.kv.backend == "redis":
        probes.append(_probe("redis", container.kv.ping()))
    checks = dict(await asyncio.gather(*probes))
    # Redis is optional: when it is down ingest still stores every sample, so only Postgres
    # decides readiness. A Redis failure is reported as degraded but stays ready.
    ok = checks["postgres"]["ok"]
    response.status_code = 200 if ok else 503
    degraded = not all(c["ok"] for c in checks.values())
    return {"status": "degraded" if degraded else "ready", "checks": checks}


@router.get("/metrics", summary="Prometheus metrics", include_in_schema=False)
async def metrics(request: Request, container: ContainerDep) -> Response:
    """GPUWatch's own metrics, then one gauge per GPU per metric for the whole fleet."""
    token = container.settings.metrics_token
    if token and not constant_time_equals(
        request.headers.get("authorization", ""), f"Bearer {token}"
    ):
        raise AuthenticationError("Send METRICS_TOKEN as a bearer token", code="metrics_token")
    body = generate_latest() + (await fleet.exposition(container)).encode()
    return Response(body, media_type=CONTENT_TYPE_LATEST)


class SystemInfo(ApiModel):
    version: str
    environment: str
    cloud: str
    key_mode: str
    storage: str
    cache_backend: str
    mail_mode: str
    dashboard_url: str
    host_offline_after_s: int
    raw_retention_days: int
    rollup_1m_retention_days: int
    rollup_1h_retention_days: int
    active_keys: int
    checks: dict[str, Any]


@router.get("/api/v1/system", response_model=SystemInfo, summary="Deployment configuration")
async def system(_: Viewer, session: SessionDep, container: ContainerDep) -> SystemInfo:
    s = container.settings
    keys = await key_service.count_active(session)
    checks: dict[str, Any] = {"postgres": {"ok": True}}
    if container.kv.backend == "redis":
        checks.update(dict([await _probe("redis", container.kv.ping())]))
    return SystemInfo(
        version=__version__,
        environment=s.environment,
        cloud=s.cloud,
        key_mode=s.key_mode,
        storage=s.storage,
        cache_backend=container.kv.backend,
        mail_mode=s.mail_mode,
        dashboard_url=s.dashboard_url,
        host_offline_after_s=s.host_offline_after_s,
        raw_retention_days=s.raw_retention_days,
        rollup_1m_retention_days=s.rollup_1m_retention_days,
        rollup_1h_retention_days=s.rollup_1h_retention_days,
        active_keys=int(keys or 0),
        checks=checks,
    )

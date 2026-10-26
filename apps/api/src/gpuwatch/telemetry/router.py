"""History and live endpoints."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import orjson
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from gpuwatch.auth.dependencies import Viewer
from gpuwatch.core.container import Container
from gpuwatch.core.deps import ContainerDep, SessionDep
from gpuwatch.fleet import service as fleet_service
from gpuwatch.fleet.schemas import GpuOut
from gpuwatch.telemetry import live, service
from gpuwatch.telemetry.schemas import FleetSeries, GpuProcesses, MetricSeries, Resolution

router = APIRouter(prefix="/api/v1", tags=["telemetry"])
STREAM_POLL_S = 1.0
HEARTBEAT_S = 15.0


def _range(
    start: datetime | None, end: datetime | None, hours: int = 1
) -> tuple[datetime, datetime]:
    end = end or datetime.now(UTC)
    return (start or end - timedelta(hours=hours)), end


@router.get("/gpus/{gpu_id}/metrics", response_model=MetricSeries, summary="GPU history")
async def gpu_metrics(
    gpu_id: uuid.UUID,
    _: Viewer,
    session: SessionDep,
    start: datetime | None = Query(None, description="Default: 1 hour before end"),
    end: datetime | None = Query(None, description="Default: now"),
    resolution: Resolution | None = Query(None, description="Default: chosen from the range"),
) -> MetricSeries:
    return await service.gpu_series(session, gpu_id, *_range(start, end), resolution)


@router.get(
    "/gpus/{gpu_id}/processes",
    response_model=GpuProcesses,
    summary="Processes on the GPU now, and workload shares over a window",
)
async def gpu_processes(
    gpu_id: uuid.UUID,
    _: Viewer,
    session: SessionDep,
    container: ContainerDep,
    window_hours: int = Query(24, ge=1, le=24 * 30),
) -> GpuProcesses:
    return await service.gpu_processes(session, container, gpu_id, window_hours)


@router.get("/fleet/series", response_model=FleetSeries, summary="Fleet-wide history")
async def fleet_series(
    _: Viewer,
    session: SessionDep,
    start: datetime | None = None,
    end: datetime | None = None,
    host_id: uuid.UUID | None = None,
) -> FleetSeries:
    return await service.fleet_series(session, *_range(start, end, hours=24), host_id)


@router.get("/live", response_model=list[GpuOut], summary="Every GPU with its newest sample")
async def live_snapshot(_: Viewer, session: SessionDep, container: ContainerDep) -> list[GpuOut]:
    return await fleet_service.list_gpus(session, container)


async def _snapshot(container: Container) -> bytes:
    async with container.db.sessionmaker() as session:
        gpus = await fleet_service.list_gpus(session, container)
    return orjson.dumps([g.model_dump(mode="json") for g in gpus])


async def _events(request: Request, container: Container) -> AsyncIterator[bytes]:
    """Server-sent events: a full snapshot whenever any agent reports, a comment as a
    heartbeat otherwise (keeps proxies from closing the connection)."""
    seen = -2
    quiet = 0.0
    while not await request.is_disconnected():
        seq = await live.sequence(container)
        if seq != seen or seq == -1:
            seen = seq
            quiet = 0.0
            yield b"event: snapshot\ndata: " + await _snapshot(container) + b"\n\n"
        elif quiet >= HEARTBEAT_S:
            quiet = 0.0
            yield b": heartbeat\n\n"
        await asyncio.sleep(STREAM_POLL_S if seq != -1 else 5.0)
        quiet += STREAM_POLL_S


@router.get(
    "/live/stream",
    summary="Live updates (server-sent events: 'snapshot' events with every GPU)",
    response_class=StreamingResponse,
)
async def live_stream(
    _: Viewer, request: Request, container: ContainerDep, session: SessionDep
) -> StreamingResponse:
    # Authentication used the request's session (the same one, cached per request), which
    # would otherwise hold a pooled connection until the stream ends: a few dozen open
    # dashboard tabs would starve every other request. Each snapshot opens its own.
    await session.close()
    return StreamingResponse(
        _events(request, container),
        media_type="text/event-stream",
        # no-transform stops compressing proxies (Next.js rewrites included) from buffering
        # the stream until it ends; x-accel-buffering does the same for nginx.
        headers={"cache-control": "no-cache, no-transform", "x-accel-buffering": "no"},
    )

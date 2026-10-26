"""Inference servers: throughput, latency and cost per token, next to the GPUs they run on."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from gpuwatch.auth.dependencies import Viewer
from gpuwatch.core.deps import SessionDep
from gpuwatch.inference import service
from gpuwatch.inference.schemas import EndpointOut, InferenceSeries

router = APIRouter(prefix="/api/v1/inference", tags=["inference"])


@router.get(
    "/endpoints", response_model=list[EndpointOut], summary="Inference servers, last 24 hours"
)
async def list_endpoints(_: Viewer, session: SessionDep) -> list[EndpointOut]:
    return await service.list_endpoints(session)


@router.get(
    "/endpoints/{endpoint_id}/series",
    response_model=InferenceSeries,
    summary="Throughput, latency percentiles and cost per token over time",
)
async def endpoint_series(
    endpoint_id: uuid.UUID,
    _: Viewer,
    session: SessionDep,
    start: datetime | None = None,
    end: datetime | None = None,
) -> InferenceSeries:
    end = end or datetime.now(UTC)
    return await service.series(session, endpoint_id, start or end - timedelta(hours=6), end)

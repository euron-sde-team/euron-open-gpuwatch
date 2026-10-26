"""Agent endpoints: enrolment and metric batches. The only routes agents call; the agent has
no inbound port and GPUWatch never sends it commands."""

from __future__ import annotations

from fastapi import APIRouter

from gpuwatch.core.deps import ContainerDep, SessionDep
from gpuwatch.fleet import service as fleet_service
from gpuwatch.ingest import service
from gpuwatch.ingest.dependencies import AgentHostDep
from gpuwatch.ingest.schemas import Batch, BatchAccepted, EnrolIn, Enrolled

router = APIRouter(prefix="/ingest/v1", tags=["ingest"])


@router.post(
    "/enroll",
    response_model=Enrolled,
    status_code=201,
    summary="Exchange an enrolment token for a host token",
)
async def enroll(data: EnrolIn, session: SessionDep, container: ContainerDep) -> Enrolled:
    return await fleet_service.enrol(session, data, container)


@router.post(
    "/batches",
    response_model=BatchAccepted,
    summary="Send one collection interval: inventory, GPU samples, processes, inference",
)
async def batches(batch: Batch, host: AgentHostDep, container: ContainerDep) -> BatchAccepted:
    return await service.store(container, host, batch)

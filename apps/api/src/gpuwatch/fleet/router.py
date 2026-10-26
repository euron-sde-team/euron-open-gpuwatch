"""Hosts, GPUs and enrolment tokens."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from gpuwatch.auth.dependencies import Admin, Viewer
from gpuwatch.core.deps import ContainerDep, SessionDep
from gpuwatch.fleet import service
from gpuwatch.fleet.schemas import (
    EnrolmentTokenCreated,
    EnrolmentTokenIn,
    EnrolmentTokenOut,
    GpuOut,
    GpuUpdate,
    HostOut,
    HostUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["fleet"])


@router.get("/hosts", response_model=list[HostOut], summary="Hosts and their agent status")
async def list_hosts(_: Viewer, session: SessionDep, container: ContainerDep) -> list[HostOut]:
    return await service.list_hosts(session, container.settings)


@router.get("/hosts/{host_id}", response_model=HostOut, summary="One host")
async def get_host(
    host_id: uuid.UUID, _: Viewer, session: SessionDep, container: ContainerDep
) -> HostOut:
    return await service.get_host(session, host_id, container.settings)


@router.patch("/hosts/{host_id}", response_model=HostOut, summary="Rename or relabel a host")
async def update_host(
    host_id: uuid.UUID,
    data: HostUpdate,
    actor: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> HostOut:
    return await service.update_host(session, host_id, data, container, actor)


@router.post(
    "/hosts/{host_id}/revoke",
    response_model=HostOut,
    summary="Stop accepting data from a host (its token stops working; history stays)",
)
async def revoke_host(
    host_id: uuid.UUID, actor: Admin, session: SessionDep, container: ContainerDep
) -> HostOut:
    return await service.revoke_host(session, host_id, container, actor)


@router.get("/gpus", response_model=list[GpuOut], summary="Every GPU with its newest sample")
async def list_gpus(
    _: Viewer,
    session: SessionDep,
    container: ContainerDep,
    host_id: uuid.UUID | None = None,
    include_retired: bool = False,
) -> list[GpuOut]:
    return await service.list_gpus(
        session, container, host_id=host_id, include_retired=include_retired
    )


@router.get("/gpus/{gpu_id}", response_model=GpuOut, summary="One GPU")
async def get_gpu(
    gpu_id: uuid.UUID, _: Viewer, session: SessionDep, container: ContainerDep
) -> GpuOut:
    return await service.get_gpu(session, gpu_id, container)


@router.patch(
    "/gpus/{gpu_id}",
    response_model=GpuOut,
    summary="Retire a GPU taken out of service (or restore it)",
)
async def update_gpu(
    gpu_id: uuid.UUID,
    data: GpuUpdate,
    actor: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> GpuOut:
    return await service.update_gpu(session, gpu_id, data, container, actor)


@router.get("/enrolment-tokens", response_model=list[EnrolmentTokenOut], summary="Enrolment tokens")
async def list_tokens(_: Admin, session: SessionDep) -> list[EnrolmentTokenOut]:
    return await service.list_tokens(session)


@router.post(
    "/enrolment-tokens",
    response_model=EnrolmentTokenCreated,
    status_code=201,
    summary="Create an enrolment token (shown once)",
)
async def create_token(
    data: EnrolmentTokenIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> EnrolmentTokenCreated:
    return await service.create_token(session, data, container.settings.api_key_pepper, actor)


@router.post(
    "/enrolment-tokens/{token_id}/revoke",
    response_model=EnrolmentTokenOut,
    summary="Revoke an enrolment token (hosts already enrolled keep working)",
)
async def revoke_token(token_id: uuid.UUID, actor: Admin, session: SessionDep) -> EnrolmentTokenOut:
    return await service.revoke_token(session, token_id, actor)

"""The overview screen."""

from __future__ import annotations

from fastapi import APIRouter

from gpuwatch.auth.dependencies import Viewer
from gpuwatch.core.deps import ContainerDep, SessionDep
from gpuwatch.overview import service
from gpuwatch.overview.schemas import Overview

router = APIRouter(prefix="/api/v1", tags=["overview"])


@router.get("/overview", response_model=Overview, summary="Fleet health, spend and top findings")
async def overview(_: Viewer, session: SessionDep, container: ContainerDep) -> Overview:
    return await service.overview(session, container)

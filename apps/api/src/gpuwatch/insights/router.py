"""Findings, the per-GPU explanation, and the engine's settings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from gpuwatch.auth.dependencies import Admin, Viewer
from gpuwatch.core.deps import ContainerDep, SessionDep
from gpuwatch.core.schemas import Ack
from gpuwatch.insights import service
from gpuwatch.insights.schemas import Explanation, InsightAction, InsightOut, InsightStatus
from gpuwatch.insights.settings import InsightSettings

router = APIRouter(prefix="/api/v1", tags=["insights"])


@router.get("/insights", response_model=list[InsightOut], summary="Findings, most costly first")
async def list_insights(
    _: Viewer,
    session: SessionDep,
    status: list[InsightStatus] | None = Query(None, description="Default: every status"),
    gpu_id: uuid.UUID | None = None,
) -> list[InsightOut]:
    return await service.list_insights(session, status, gpu_id)


@router.post(
    "/insights/{insight_id}/actions",
    response_model=InsightOut,
    summary="Acknowledge, dismiss or reopen a finding",
)
async def act(
    insight_id: uuid.UUID, data: InsightAction, actor: Admin, session: SessionDep
) -> InsightOut:
    return await service.act(session, insight_id, data, actor)


@router.post("/insights/evaluate", response_model=Ack, summary="Re-run the engine now")
async def evaluate(_: Admin, container: ContainerDep) -> Ack:
    count = await service.evaluate(container)
    return Ack(message=f"{count} findings")


@router.get(
    "/gpus/{gpu_id}/explain",
    response_model=Explanation,
    summary="Why this GPU is expensive or slow, in plain sentences",
)
async def explain(gpu_id: uuid.UUID, _: Viewer, session: SessionDep) -> Explanation:
    return await service.explain(session, gpu_id)


@router.get(
    "/settings/insights", response_model=InsightSettings, summary="Idle rule and thresholds"
)
async def get_settings(_: Viewer, session: SessionDep) -> InsightSettings:
    return await service.get_settings(session)


@router.put("/settings/insights", response_model=InsightSettings, summary="Change them")
async def put_settings(data: InsightSettings, actor: Admin, session: SessionDep) -> InsightSettings:
    return await service.put_settings(session, data, actor)

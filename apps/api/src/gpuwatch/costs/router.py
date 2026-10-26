"""Costs: rates, workload rules, summaries, series and CSV reports."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, Response

from gpuwatch.auth.dependencies import Admin, Viewer
from gpuwatch.core.deps import ContainerDep, SessionDep
from gpuwatch.core.schemas import Ack
from gpuwatch.costs import service
from gpuwatch.costs.schemas import (
    CostSeries,
    CostSummary,
    GroupBy,
    RateIn,
    RateOut,
    RateUpdate,
    ReportIn,
    ReportOut,
    WorkloadRuleIn,
    WorkloadRuleOut,
)

router = APIRouter(prefix="/api/v1", tags=["costs"])


def _range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    end = end or datetime.now(UTC)
    return (start or end - timedelta(days=7)), end


@router.get("/costs", response_model=CostSummary, summary="Cost over a window, grouped")
async def cost_summary(
    _: Viewer,
    session: SessionDep,
    group_by: GroupBy = "workload",
    start: datetime | None = Query(None, description="Default: 7 days before end"),
    end: datetime | None = Query(None, description="Default: now"),
) -> CostSummary:
    return await service.summary(session, *_range(start, end), group_by)


@router.get("/costs/series", response_model=CostSeries, summary="Cost over time, grouped")
async def cost_series(
    _: Viewer,
    session: SessionDep,
    group_by: GroupBy = "workload",
    start: datetime | None = None,
    end: datetime | None = None,
) -> CostSeries:
    return await service.series(session, *_range(start, end), group_by)


@router.get("/rates", response_model=list[RateOut], summary="Hourly rates")
async def list_rates(_: Viewer, session: SessionDep) -> list[RateOut]:
    return await service.list_rates(session)


@router.post("/rates", response_model=RateOut, status_code=201, summary="Set a rate")
async def create_rate(data: RateIn, actor: Admin, session: SessionDep) -> RateOut:
    return await service.create_rate(session, data, actor)


@router.patch("/rates/{rate_id}", response_model=RateOut, summary="Change a rate")
async def update_rate(
    rate_id: uuid.UUID, data: RateUpdate, actor: Admin, session: SessionDep
) -> RateOut:
    return await service.update_rate(session, rate_id, data, actor)


@router.delete("/rates/{rate_id}", response_model=Ack, summary="Remove a rate")
async def delete_rate(rate_id: uuid.UUID, actor: Admin, session: SessionDep) -> Ack:
    await service.delete_rate(session, rate_id, actor)
    return Ack()


@router.get("/workload-rules", response_model=list[WorkloadRuleOut], summary="Workload rules")
async def list_rules(_: Viewer, session: SessionDep) -> list[WorkloadRuleOut]:
    return await service.list_rules(session)


@router.post(
    "/workload-rules", response_model=WorkloadRuleOut, status_code=201, summary="Add a rule"
)
async def create_rule(data: WorkloadRuleIn, actor: Admin, session: SessionDep) -> WorkloadRuleOut:
    return await service.create_rule(session, data, actor)


@router.put("/workload-rules/{rule_id}", response_model=WorkloadRuleOut, summary="Edit a rule")
async def update_rule(
    rule_id: uuid.UUID, data: WorkloadRuleIn, actor: Admin, session: SessionDep
) -> WorkloadRuleOut:
    return await service.update_rule(session, rule_id, data, actor)


@router.delete("/workload-rules/{rule_id}", response_model=Ack, summary="Delete a rule")
async def delete_rule(rule_id: uuid.UUID, actor: Admin, session: SessionDep) -> Ack:
    await service.delete_rule(session, rule_id, actor)
    return Ack()


@router.post(
    "/workload-rules/apply",
    response_model=Ack,
    summary="Re-attribute every hour that still has raw samples with the current rules",
)
async def apply_rules(actor: Admin, session: SessionDep, container: ContainerDep) -> Ack:
    hosts = await service.reattribute(session, container, actor)
    return Ack(message=f"Re-attributing {hosts} hosts; costs update within a minute")


@router.get("/reports", response_model=list[ReportOut], summary="Generated reports")
async def list_reports(_: Viewer, session: SessionDep) -> list[ReportOut]:
    return await service.list_reports(session)


@router.post("/reports", response_model=ReportOut, status_code=201, summary="Export a CSV")
async def create_report(
    data: ReportIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> ReportOut:
    return await service.create_report(session, container, data, actor)


@router.get("/reports/{report_id}/download", summary="Download a report CSV")
async def download_report(
    report_id: uuid.UUID, _: Viewer, session: SessionDep, container: ContainerDep
) -> Response:
    filename, body = await service.report_file(session, container, report_id)
    return Response(
        body,
        media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )

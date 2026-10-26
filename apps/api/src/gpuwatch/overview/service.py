"""The home screen in one call: fleet health, spend, waste and what to look at first."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.alerts import service as alert_service
from gpuwatch.core.container import Container
from gpuwatch.costs import service as cost_service
from gpuwatch.fleet import service as fleet_service
from gpuwatch.insights import service as insight_service
from gpuwatch.overview.schemas import Overview

WASTE_KINDS = {"idle_loaded", "idle_empty", "oversized_vram"}


async def overview(session: AsyncSession, container: Container) -> Overview:
    now = datetime.now(UTC)
    hosts = await fleet_service.list_hosts(session, container.settings)
    gpus = await fleet_service.list_gpus(session, container)
    utils = [g.live["util_gpu"] for g in gpus if g.live and g.live.get("util_gpu") is not None]
    week = await cost_service.summary(session, now - timedelta(days=7), now, "workload")
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month = (
        await cost_service.summary(session, month_start, now, "host") if now > month_start else None
    )
    insights = await insight_service.list_insights(session, status=["open", "acknowledged"])
    waste = sum(i.est_monthly_nusd or 0 for i in insights if i.kind in WASTE_KINDS)
    return Overview(
        hosts_total=len([h for h in hosts if h.status != "revoked"]),
        hosts_online=len([h for h in hosts if h.status == "online"]),
        hosts_degraded=len(
            [h for h in hosts if h.status == "online" and h.agent_status == "degraded"]
        ),
        gpus_total=len(gpus),
        gpus_reporting=len([g for g in gpus if g.status == "ok"]),
        gpus_lost=len([g for g in gpus if g.status == "lost"]),
        util_now_avg=sum(utils) / len(utils) if utils else None,
        alerts_firing=await alert_service.firing_count(session),
        insights_open=len([i for i in insights if i.status == "open"]),
        spend_7d_nusd=week.total_nusd,
        idle_7d_nusd=week.idle_nusd + week.held_idle_nusd,
        spend_month_nusd=month.total_nusd if month else 0,
        unpriced_gpu_hours_7d=week.unpriced_gpu_hours,
        est_monthly_waste_nusd=waste,
        rates_set=await cost_service.rate_count(session) > 0,
        top_workloads=week.rows[:6],
        top_insights=insights[:5],
    )

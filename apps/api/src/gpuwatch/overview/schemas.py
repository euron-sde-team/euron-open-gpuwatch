"""Public contract of the overview."""

from __future__ import annotations

from gpuwatch.core.schemas import ApiModel
from gpuwatch.costs.schemas import CostRow
from gpuwatch.insights.schemas import InsightOut


class Overview(ApiModel):
    hosts_total: int
    hosts_online: int
    hosts_degraded: int
    gpus_total: int
    gpus_reporting: int
    gpus_lost: int
    util_now_avg: float | None
    alerts_firing: int
    insights_open: int
    spend_7d_nusd: int
    idle_7d_nusd: int
    spend_month_nusd: int
    unpriced_gpu_hours_7d: float
    est_monthly_waste_nusd: int
    rates_set: bool
    top_workloads: list[CostRow]
    top_insights: list[InsightOut]

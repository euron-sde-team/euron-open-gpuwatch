"""Which hourly rate applies to each GPU: the GPU's own, else its host's, else its model's."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.costs.models import GpuRate
from gpuwatch.fleet.models import Gpu


@dataclass(frozen=True, slots=True)
class AppliedRate:
    nusd_per_hour: int
    scope: str


def pick(
    gpu_id: uuid.UUID,
    host_id: uuid.UUID,
    model: str,
    by_gpu: dict[uuid.UUID, int],
    by_host: dict[uuid.UUID, int],
    by_model: dict[str, int],
) -> AppliedRate | None:
    if gpu_id in by_gpu:
        return AppliedRate(by_gpu[gpu_id], "gpu")
    if host_id in by_host:
        return AppliedRate(by_host[host_id], "host")
    if model in by_model:
        return AppliedRate(by_model[model], "model")
    return None


async def applied_rates(session: AsyncSession) -> dict[uuid.UUID, AppliedRate]:
    """Rate per GPU id, for every GPU that has one."""
    rates = (await session.scalars(select(GpuRate))).all()
    by_gpu = {r.gpu_id: r.nusd_per_hour for r in rates if r.scope == "gpu" and r.gpu_id}
    by_host = {r.host_id: r.nusd_per_hour for r in rates if r.scope == "host" and r.host_id}
    by_model = {r.gpu_model: r.nusd_per_hour for r in rates if r.scope == "model" and r.gpu_model}
    out: dict[uuid.UUID, AppliedRate] = {}
    for gpu_id, host_id, name in (
        await session.execute(select(Gpu.id, Gpu.host_id, Gpu.name))
    ).all():
        rate = pick(gpu_id, host_id, name, by_gpu, by_host, by_model)
        if rate is not None:
            out[gpu_id] = rate
    return out


def seconds_cost(seconds: float, nusd_per_hour: int) -> int:
    """Cost of ``seconds`` at an hourly rate, rounded to the nearest nano-dollar."""
    return round(seconds * nusd_per_hour / 3600)

"""The idle rule and insight thresholds, editable in the dashboard (Settings, Insights).

Stored as one JSON document in ``app_settings``; missing keys fall back to the defaults
below, so adding a setting never needs a migration.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from gpuwatch.core.schemas import ApiModel
from gpuwatch.insights.models import AppSetting

KEY = "insights"


class InsightSettings(ApiModel):
    # Idle rule: a minute is idle when average utilization is below this...
    idle_util_pct: Annotated[float, Field(ge=0, le=50)] = 5.0
    # ...and a run of idle minutes counts once it lasts this long.
    idle_min_minutes: Annotated[int, Field(ge=5, le=1440)] = 30
    # ...and a GPU is reported once such runs add up to this share of its monitored time
    # (a nightly checkpoint gap of an hour is normal; a GPU idle a third of the week is not).
    idle_min_share: Annotated[float, Field(ge=0, le=1)] = 0.1
    # A GPU is "held" (a model loaded) when it has processes or this share of VRAM in use.
    held_mem_pct: Annotated[float, Field(ge=1, le=90)] = 10.0
    # Spend findings look this far back; health findings look back one day.
    window_days: Annotated[int, Field(ge=1, le=30)] = 7
    # Underused: busy for at least this many hours at an average below this utilization.
    underused_util_pct: Annotated[float, Field(ge=5, le=90)] = 30.0
    underused_min_hours: Annotated[float, Field(ge=1, le=168)] = 6.0
    # Oversized: peak VRAM below this share of the card over at least a day of data.
    oversized_peak_pct: Annotated[float, Field(ge=5, le=90)] = 40.0
    # Throttled: slowed down for at least this share of busy time.
    throttle_pct: Annotated[float, Field(ge=1, le=100)] = 10.0
    # Memory pressure: VRAM at or above this share for at least the given minutes.
    mem_pressure_pct: Annotated[float, Field(ge=50, le=100)] = 95.0
    mem_pressure_minutes: Annotated[int, Field(ge=1, le=1440)] = 10
    # Inference: KV cache at or above this share with requests waiting.
    kv_cache_full: Annotated[float, Field(ge=0.5, le=1)] = 0.9
    queue_minutes: Annotated[int, Field(ge=1, le=1440)] = 15
    overprovisioned_util_pct: Annotated[float, Field(ge=1, le=90)] = 20.0


async def load(conn: AsyncSession | AsyncConnection) -> InsightSettings:
    raw = await conn.scalar(select(AppSetting.value).where(AppSetting.key == KEY))
    return InsightSettings.model_validate(raw or {})

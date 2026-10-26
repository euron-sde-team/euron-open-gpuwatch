"""Retention and partition upkeep.

Raw sample partitions are dropped whole once their day is past the raw retention *and*
the rollup watermark has passed it (so nothing is dropped before it was rolled up).
Rollups, usage and housekeeping tables are trimmed with bounded DELETEs.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from gpuwatch.core.container import Container
from gpuwatch.core.storage import ObjectNotFoundError
from gpuwatch.costs.models import Report
from gpuwatch.telemetry import partitions
from gpuwatch.telemetry.models import JobState

log = logging.getLogger("gpuwatch.retention")
AHEAD_DAYS = 3


async def ensure_partitions(container: Container, now: datetime | None = None) -> None:
    today = (now or datetime.now(UTC)).date()
    await partitions.ensure(
        container.db.engine, {today + timedelta(days=d) for d in range(-1, AHEAD_DAYS + 1)}
    )


async def run(container: Container, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    s = container.settings
    counts: dict[str, int] = {}
    async with container.db.engine.connect() as conn:
        watermark = await conn.scalar(select(JobState.watermark).where(JobState.name == "rollup"))
    raw_cutoff = now - timedelta(days=s.raw_retention_days)
    if watermark is not None:
        cutoff = min(raw_cutoff, watermark).date()
        counts["partitions"] = len(await partitions.drop_before(container.db.engine, cutoff))
    deletes = {
        "gpu_rollups_1m": ("bucket", now - timedelta(days=s.rollup_1m_retention_days)),
        "gpu_rollups_1h": ("bucket", now - timedelta(days=s.rollup_1h_retention_days)),
        "workload_usage_1h": ("bucket", now - timedelta(days=s.rollup_1h_retention_days)),
        "inference_rollups_1h": ("bucket", now - timedelta(days=s.rollup_1h_retention_days)),
        "inference_samples": ("ts", raw_cutoff),
        "ingest_batches": ("received_at", now - timedelta(days=2)),
    }
    async with container.db.engine.begin() as conn:
        for table, (column, before) in deletes.items():
            result = await conn.execute(
                text(f"DELETE FROM {table} WHERE {column} < :before"),
                {"before": before},
            )
            counts[table] = int(result.rowcount or 0)
        result = await conn.execute(
            text(
                "DELETE FROM notifications WHERE created_at < :before "
                "AND (delivered_at IS NOT NULL OR failed_at IS NOT NULL)"
            ),
            {"before": now - timedelta(days=30)},
        )
        counts["notifications"] = int(result.rowcount or 0)
    async with container.db.sessionmaker() as session:
        old = (
            await session.scalars(
                select(Report).where(
                    Report.created_at < now - timedelta(days=s.report_retention_days)
                )
            )
        ).all()
        for report in old:
            with contextlib.suppress(ObjectNotFoundError):
                await container.storage.delete(report.object_key)
            await session.delete(report)
        await session.commit()
        counts["reports"] = len(old)
    return counts

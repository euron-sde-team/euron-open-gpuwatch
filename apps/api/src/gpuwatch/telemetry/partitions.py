"""Daily partitions of the raw sample tables.

The worker creates partitions a few days ahead; ingest creates one on demand for a day it
has not seen (a spool replay, a demo backfill). Retention drops whole partitions, which is
instant and leaves no bloat, unlike DELETE.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

PARTITIONED = ("gpu_samples", "process_samples")
_NAME = re.compile(r"^(gpu_samples|process_samples)_p(\d{8})$")
# Days this process already ensured, so the hot path does not repeat catalog checks.
_ensured: set[tuple[str, date]] = set()


def partition_name(table: str, day: date) -> str:
    return f"{table}_p{day:%Y%m%d}"


async def ensure(engine: AsyncEngine, days: set[date]) -> None:
    """Create the partitions for ``days`` (both tables) unless they exist."""
    missing = sorted(
        (table, day) for table in PARTITIONED for day in days if (table, day) not in _ensured
    )
    if not missing:
        return
    async with engine.begin() as conn:
        # One creator at a time across replicas; CREATE ... IF NOT EXISTS is not race free.
        await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('gpuwatch:partitions'))"))
        for table, day in missing:
            start = datetime(day.year, day.month, day.day, tzinfo=UTC)
            end = start + timedelta(days=1)
            await conn.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {partition_name(table, day)} "
                    f"PARTITION OF {table} FOR VALUES FROM ('{start.isoformat()}') "
                    f"TO ('{end.isoformat()}')"
                )
            )
    _ensured.update(missing)


async def existing(engine: AsyncEngine) -> list[tuple[str, date]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
                "JOIN pg_class p ON p.oid = i.inhparent WHERE p.relname = ANY(:tables)"
            ),
            {"tables": list(PARTITIONED)},
        )
        out = []
        for (name,) in rows:
            m = _NAME.match(name)
            if m:
                out.append((m.group(1), datetime.strptime(m.group(2), "%Y%m%d").date()))
        return sorted(out)


async def drop_before(engine: AsyncEngine, cutoff: date) -> list[str]:
    """Drop every partition whose whole day is before ``cutoff``."""
    dropped = []
    for table, day in await existing(engine):
        if day < cutoff:
            async with engine.begin() as conn:
                await conn.execute(text(f"DROP TABLE IF EXISTS {partition_name(table, day)}"))
            _ensured.discard((table, day))
            dropped.append(partition_name(table, day))
    return dropped


def forget() -> None:
    """Tests drop and recreate schemas; the in-process memo must not outlive them."""
    _ensured.clear()

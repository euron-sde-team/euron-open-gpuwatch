"""The live view: the latest sample of every GPU, kept in the KV store (Redis, or process
memory without it) so the dashboard never scans the sample tables to show "now".

Postgres is the source of truth. If the KV store is down or evicted a key, the live view
falls back to the newest stored sample of that GPU.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

import orjson
from redis.exceptions import RedisError
from sqlalchemy import text

from gpuwatch.core.container import Container
from gpuwatch.observability import metrics

log = logging.getLogger("gpuwatch.live")
SEQ_KEY = "gw:live:seq"


def gpu_key(gpu_id: uuid.UUID) -> str:
    return f"gw:live:gpu:{gpu_id}"


async def publish(container: Container, latest: dict[uuid.UUID, dict[str, Any]]) -> None:
    """Store each GPU's newest sample and bump the sequence the stream watches."""
    if not latest:
        return
    ttl = container.settings.live_ttl_s
    try:
        for gpu_id, sample in latest.items():
            await container.kv.set(gpu_key(gpu_id), orjson.dumps(sample), ttl)
        await container.kv.incr(SEQ_KEY)
    except (RedisError, OSError):
        metrics.DEPENDENCY_ERRORS.labels("redis", "live_publish").inc()


async def sequence(container: Container) -> int:
    try:
        raw = await container.kv.get(SEQ_KEY)
    except (RedisError, OSError):
        return -1
    return int(raw or b"0")


_FALLBACK = text(
    """
    SELECT DISTINCT ON (gpu_id) gpu_id, ts, interval_s, util_gpu, util_mem, mem_used_mib,
           mem_total_mib, temp_c, power_w, power_limit_w, fan_pct, sm_clock_mhz,
           mem_clock_mhz, pstate, throttle_reasons, pcie_rx_kbps, pcie_tx_kbps,
           ecc_uncorrected, xid, procs
    FROM gpu_samples
    WHERE gpu_id = ANY(:ids) AND ts > now() - make_interval(secs => :ttl)
    ORDER BY gpu_id, ts DESC
    """
)


async def latest(container: Container, gpu_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    """Newest sample per GPU (from the KV store, else Postgres). Missing: no recent data."""
    out: dict[uuid.UUID, dict[str, Any]] = {}
    if not gpu_ids:
        return out
    try:
        values = await container.kv.mget([gpu_key(g) for g in gpu_ids])
    except (RedisError, OSError):
        metrics.DEPENDENCY_ERRORS.labels("redis", "live_read").inc()
        values = [None] * len(gpu_ids)
    missing = []
    for gpu_id, raw in zip(gpu_ids, values, strict=True):
        if raw is None:
            missing.append(gpu_id)
        else:
            out[gpu_id] = orjson.loads(raw)
    if missing:
        async with container.db.engine.connect() as conn:
            rows = await conn.execute(
                _FALLBACK, {"ids": missing, "ttl": container.settings.live_ttl_s}
            )
            for row in rows.mappings():
                sample = dict(row)
                gpu_id = sample.pop("gpu_id")
                ts: datetime = sample["ts"]
                sample["ts"] = ts.isoformat()
                out[gpu_id] = sample
    return out

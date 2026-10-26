"""Background worker: rollups and attribution, alert evaluation, notifications, insights,
partition upkeep and retention.

Stateless and safe to run as several replicas: each job takes a Postgres advisory lock (or
claims rows with ``FOR UPDATE SKIP LOCKED``), so two workers never do the same work. SIGTERM
finishes the job in hand, then exits. Prometheus metrics are served on WORKER_METRICS_PORT.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from prometheus_client import start_http_server

from gpuwatch.alerts import evaluator, notifier
from gpuwatch.core.config import get_settings
from gpuwatch.core.container import Container
from gpuwatch.core.db import import_all_models
from gpuwatch.core.logs import configure_logging
from gpuwatch.insights import service as insights
from gpuwatch.observability import metrics
from gpuwatch.telemetry import retention, rollups

log = logging.getLogger("gpuwatch.worker")


@dataclass
class Job:
    name: str
    every_s: float
    run: Callable[[Container], Awaitable[Any]]
    last: float = field(default=0.0)


def jobs(container: Container) -> list[Job]:
    s = container.settings
    return [
        Job("partitions", 3600, retention.ensure_partitions),
        Job("rollup", s.worker_tick_s, rollups.tick),
        Job("alerts", s.alert_eval_interval_s, evaluator.evaluate),
        Job("notifications", 2.0, notifier.deliver_pending),
        Job("insights", s.insight_eval_interval_s, insights.evaluate),
        Job("retention", 3600, retention.run),
    ]


async def run_due(container: Container, schedule: list[Job], now: float | None = None) -> int:
    """Run every job whose interval elapsed. A failing job is logged and retried next time;
    it never stops the others."""
    now = now if now is not None else time.monotonic()
    ran = 0
    for job in schedule:
        if now - job.last < job.every_s:
            continue
        job.last = now
        started = time.perf_counter()
        try:
            await job.run(container)
        except Exception:
            metrics.JOB_FAILURES.labels(job.name).inc()
            log.exception("job failed", extra={"job": job.name})
        finally:
            metrics.JOB_SECONDS.labels(job.name).observe(time.perf_counter() - started)
        ran += 1
    return ran


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    import_all_models()
    if settings.worker_metrics_port:
        start_http_server(settings.worker_metrics_port)
    container = Container.build(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    schedule = jobs(container)
    log.info("worker started", extra={"cache": container.kv.backend, "mail": settings.mail_mode})
    try:
        while not stop.is_set():
            await run_due(container, schedule)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=1.0)
    finally:
        await container.close()
        log.info("worker stopped")

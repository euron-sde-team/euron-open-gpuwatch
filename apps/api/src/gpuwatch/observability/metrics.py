"""Prometheus metrics for GPUWatch itself (ingest, jobs, alerts, notifications).

The fleet's GPU metrics are exposed separately, as gauges computed on scrape from the live
view (``observability/fleet.py``), so an existing Prometheus or Grafana can read every
GPU GPUWatch knows about without running its own exporters.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

_S_BUCKETS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)

INGEST_BATCHES = Counter("gpuwatch_ingest_batches_total", "Agent batches by outcome", ["outcome"])
INGEST_ROWS = Counter("gpuwatch_ingest_rows_total", "Rows stored from agents", ["kind"])
INGEST_DROPPED = Counter(
    "gpuwatch_ingest_dropped_total",
    "Rows refused at ingest (outside the time window, unknown GPU)",
    ["reason"],
)
INGEST_SECONDS = Histogram(
    "gpuwatch_ingest_seconds", "Time to store one agent batch", buckets=_S_BUCKETS
)
ENROLMENTS = Counter("gpuwatch_enrolments_total", "Agent enrolments by outcome", ["outcome"])
JOB_SECONDS = Histogram("gpuwatch_job_seconds", "Worker job run time", ["job"], buckets=_S_BUCKETS)
JOB_FAILURES = Counter("gpuwatch_job_failures_total", "Worker job failures", ["job"])
ALERTS = Counter("gpuwatch_alerts_total", "Alert transitions", ["kind", "transition"])
NOTIFICATIONS = Counter(
    "gpuwatch_notifications_total", "Notification deliveries", ["channel", "outcome"]
)
INSIGHTS = Counter("gpuwatch_insights_total", "Insight transitions", ["kind", "transition"])
DEPENDENCY_ERRORS = Counter(
    "gpuwatch_dependency_errors_total",
    "Optional dependency failures that were absorbed",
    ["dependency", "operation"],
)

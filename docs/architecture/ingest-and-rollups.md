# Ingest and Rollups

How a batch from an agent becomes rows, how rows become minute and hour buckets, and how
old data leaves. Code: [`ingest/service.py`](../../apps/api/src/gpuwatch/ingest/service.py),
[`telemetry/partitions.py`](../../apps/api/src/gpuwatch/telemetry/partitions.py),
[`telemetry/rollups.py`](../../apps/api/src/gpuwatch/telemetry/rollups.py),
[`telemetry/retention.py`](../../apps/api/src/gpuwatch/telemetry/retention.py).

- [The batch](#the-batch)
- [Storing a batch](#storing-a-batch)
- [Idempotency](#idempotency)
- [Partitions](#partitions)
- [Rollups](#rollups)
- [The lag/2 rule](#the-lag2-rule)
- [Retention](#retention)
- [Tests](#tests)

## The batch

One batch carries one collection interval of one host
([`ingest/schemas.py`](../../apps/api/src/gpuwatch/ingest/schemas.py)):

```json
{
  "batch_id": "6f0c...uuid",
  "agent": {"version": "0.1.0", "collector": "nvml", "hostname": "train-node-01",
            "driver_version": "550.127.05", "cuda_version": "12.4", "interval_s": 5,
            "status": "ok", "problems": []},
  "gpus": [{"uuid": "GPU-...", "index": 0, "name": "NVIDIA H100 80GB HBM3",
            "memory_total_mib": 81559, "power_limit_w": 700, "pci_bus_id": "...", "mig_mode": false}],
  "samples": [{"gpu_uuid": "GPU-...", "ts": "2026-10-26T10:00:05Z", "interval_s": 5,
               "util_gpu": 97, "mem_used_mib": 70211, "fan_pct": null, "throttle_reasons": 4}],
  "processes": [{"gpu_uuid": "GPU-...", "ts": "2026-10-26T10:00:05Z", "pid": 4242,
                 "name": "python3", "username": "li", "container_id": "3f2a9c1b7d0e",
                 "mem_used_mib": 65000, "sm_util": 96}],
  "inference": [{"endpoint": "llama-chat", "kind": "vllm", "url": "http://...:8000/metrics",
                 "gpu_uuids": ["GPU-..."], "ts": "...", "interval_s": 5, "up": true,
                 "requests": 12, "prompt_tokens": 9400, "generation_tokens": 3100,
                 "running": 7, "waiting": 0, "kv_cache_usage": 0.41,
                 "ttft": {"0.1": 4, "0.25": 7, "+Inf": 1}}]
}
```

Every metric is optional. `null` means the driver did not report it and is stored as NULL.
`interval_s` on a sample is the time since the agent's previous reading (capped at three
configured intervals), so a sample always stands for the time it covers.

The reply is `{accepted, duplicate, samples, processes, inference, dropped, next_in_s}`.

## Storing a batch

`store(container, host, batch)` runs after the host token and rate limit checks:

1. **Row limit.** If samples plus processes plus inference rows exceed
   `INGEST_MAX_SAMPLES`, the whole batch is refused (`batch_too_large`).
2. **Time window.** Rows outside `[now - days, now + INGEST_MAX_FUTURE_S]` are dropped,
   where `days` is `RAW_RETENTION_DAYS`, or `SIMULATED_BACKFILL_DAYS` for a simulated
   host. Drops are counted in `gpuwatch_ingest_dropped_total{reason="time_window"}` and in
   the reply's `dropped`.
3. **Partitions.** The UTC days of the remaining samples and processes are ensured to have
   partitions (see [Partitions](#partitions)).
4. **One transaction:**
   1. `INSERT INTO ingest_batches (host_id, batch_id) ON CONFLICT DO NOTHING RETURNING`.
      No row returned means the batch was already stored: roll back and reply
      `duplicate: true`.
   2. Lock the host row and update its agent version, collector, OS, driver, CUDA,
      interval, status, problems and `last_seen_at`.
   3. Upsert the declared GPUs by NVIDIA UUID (`ON CONFLICT (uuid) DO UPDATE`), which
      also moves a card to this host and clears `retired_at`.
   4. Drop samples and processes for UUIDs the batch did not declare
      (`reason="unknown_gpu"`).
   5. Bulk insert samples and processes with `executemany` and `ON CONFLICT DO NOTHING`.
   6. Upsert inference endpoints by `(host_id, name)` (keeping the last known model when
      the server does not report one) and insert their samples.
   7. Record a dirty range when the batch holds rows old enough that the rollup job may
      already have closed their minutes ([The lag/2 rule](#the-lag2-rule)).
5. **Live publish**, after the commit: each GPU's newest sample, if it is younger than
   `LIVE_TTL_S`, goes to `gw:live:gpu:<id>` and `gw:live:seq` is incremented. A KV error
   here is counted and ignored.

## Idempotency

An agent may send the same batch twice: it spooled a batch, sent it, and lost the reply.
Two layers make that harmless:

- **Batch ids.** `ingest_batches` has the primary key `(host_id, batch_id)`. The second
  arrival writes nothing and returns `duplicate: true`, so the agent drops it from the
  spool. Batch ids are kept for 2 days.
- **Row keys.** `gpu_samples (gpu_id, ts)`, `process_samples (gpu_id, ts, pid)` and
  `inference_samples (endpoint_id, ts)` ignore duplicates, so even a replay older than the
  batch id retention cannot double a sample.

Concurrent batches from one host all land: each runs in its own transaction and locks the
host row only to update it (`test_concurrent_batches_from_one_host_all_land`).

## Partitions

`gpu_samples` and `process_samples` are range-partitioned by UTC day
(`<table>_pYYYYMMDD`).

- The worker's `partitions` job creates yesterday to three days ahead every hour.
- Ingest creates a partition on demand for a day it has not seen (a spool replay, a demo
  backfill).
- Creation takes `pg_advisory_xact_lock(hashtext('gpuwatch:partitions'))`, because
  `CREATE TABLE IF NOT EXISTS ... PARTITION OF` is not race free across replicas.
- Each process remembers which `(table, day)` pairs it ensured, so the hot path does not
  repeat catalog checks.

Dropping a whole partition is instant and leaves no bloat, unlike `DELETE`.

## Rollups

Two tables, `gpu_rollups_1m` and `gpu_rollups_1h`, keyed by `(gpu_id, bucket)`. Every
recompute is an idempotent `INSERT ... ON CONFLICT DO UPDATE` of whole buckets from their
source rows, so recomputing a range twice gives the same result.

**Minute buckets** aggregate raw samples: count, summed `interval_s`, averages and maxima
of each metric over the samples that reported it, energy
(`sum(power_w * interval_s) / 3600`), busy seconds (utilization at or above 50%) and, of
those busy seconds, the seconds slowed by power (`SW_POWER_CAP | HW_POWER_BRAKE`),
thermal (`SW_THERMAL | HW_THERMAL`) and hardware (`HW_SLOWDOWN`) throttle reasons. Busy
and throttle seconds are NULL when the GPU reported no utilization or no throttle reasons,
so "not reported" never turns into "0 seconds".

**Hour buckets** aggregate minute buckets with seconds-weighted averages over the minutes
that reported each metric, maxima, and sums of seconds, energy, busy and throttle time.

`tick()` runs every `WORKER_TICK_S` under `pg_try_advisory_xact_lock('gpuwatch:rollup')`
(other replicas skip the tick):

1. **Watermark.** `target = floor_minute(now - ROLLUP_LAG_S)`. On the first run the
   watermark starts at the oldest raw sample (or the target, with no data). If
   `target > watermark`, `recompute(watermark, target)` and store `target` in
   `job_state`. Rows that arrive within the lag are included naturally.
2. **Dirty ranges.** Up to 500 `rollup_dirty` rows are read, merged into one covering
   range per host, recomputed for that host only, and deleted after the recompute. A crash
   between the two leaves them queued; the recompute is idempotent.

`recompute(start, end, host)` works in steps of at most 6 hours (a 30-day backfill runs in
many short transactions). Each step rebuilds the minute buckets, the hours that contain
them, then cost attribution ([cost-attribution.md](cost-attribution.md)) and hourly
inference rollups for those hours, in one transaction.

## The lag/2 rule

The watermark path closes minutes older than `now - ROLLUP_LAG_S` (90 s by default). A row
older than that arrives after its minute was closed, so ingest must queue it as a dirty
range. The boundary is not sharp: an ingest transaction that started earlier can commit
while the rollup job is computing the range that contains its rows, and the rollup's
snapshot would not see them.

So ingest queues a dirty range whenever the batch's oldest row is older than
`now - ROLLUP_LAG_S / 2` (45 s by default), not only older than the full lag. The range
is `[oldest row, newest row + 1 s)`. Rows between half the lag and the full lag may be
rolled up twice, which is harmless because recompute is idempotent. For a row to slip
between the two paths unseen, the ingest transaction would have to take longer than half
the lag between its `now` and its commit.

Live batches (rows a few seconds old) never create dirty ranges. Spool replays after an
outage and simulated backfills do.

## Retention

The `retention` job runs hourly:

- **Raw partitions** are dropped whole when their day is before
  `min(now - RAW_RETENTION_DAYS, rollup watermark)`. Nothing is dropped before it has been
  rolled up; with no watermark yet, nothing is dropped.
- **Range deletes:** minute rollups past `ROLLUP_1M_RETENTION_DAYS`; hour rollups, hourly
  workload usage and hourly inference rollups past `ROLLUP_1H_RETENTION_DAYS`; inference
  samples past `RAW_RETENTION_DAYS`; batch ids past 2 days; notifications delivered or
  failed more than 30 days ago.
- **Reports** past `REPORT_RETENTION_DAYS` are deleted from object storage and from the
  table.

Cost attribution reads raw samples, so hours older than the raw retention keep the
attribution they had when they were rolled up; re-applying workload rules
(`POST /api/v1/workload-rules/apply`) reaches back only as far as raw samples exist.

## Tests

| Behaviour | Test |
| --------- | ---- |
| A batch updates the host and inventory | `tests/integration/test_fleet.py::test_a_batch_updates_the_host_and_inventory` |
| Rows outside the window are dropped; simulated hosts may backfill | `test_fleet.py::test_samples_outside_the_time_window_are_dropped`, `test_simulated_hosts_may_backfill_history` |
| A GPU that moves hosts follows its UUID | `test_fleet.py::test_a_gpu_that_moves_hosts_follows_its_uuid` |
| Late samples are rolled up exactly once | `tests/integration/test_telemetry.py::test_late_samples_are_rolled_up_exactly_once` |
| History resolution follows the range | `test_telemetry.py::test_series_resolution_follows_the_range` |
| One rollup worker at a time across replicas | `test_telemetry.py::test_rollup_runs_once_across_replicas` |
| Retention drops only rolled-up partitions; partitions are created ahead | `test_telemetry.py::test_retention_drops_only_rolled_up_partitions`, `test_partitions_are_created_ahead` |
| Spool and replay without duplicates; resending is a no-op | `tests/integration/test_acceptance.py::test_7_the_agent_spools_while_the_server_is_down_and_replays_without_duplicates`, `test_7_resending_a_batch_is_a_no_op` |
| Unreported metrics stay null everywhere | `test_acceptance.py::test_2_a_metric_the_driver_does_not_report_stays_null_everywhere` |
| Concurrent batches from one host all land | `tests/integration/test_hardening.py::test_concurrent_batches_from_one_host_all_land` |

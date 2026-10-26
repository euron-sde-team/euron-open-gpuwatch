# ADR-0005: Rollups with a watermark and dirty ranges

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

Dashboards, insights and costs read minute and hour buckets, not raw rows. Data does not
always arrive in order: an agent replays its spool after an outage, a simulated host
backfills 30 days, a batch commits a few seconds late. A rollup that only processes "the
last minute" would miss those rows; recomputing everything is too expensive; incremental
`+=` updates double count on retries.

## Decision

- **Idempotent recompute of whole buckets.** `recompute(start, end, host)` rebuilds every
  minute bucket in the range from raw samples with `INSERT ... ON CONFLICT DO UPDATE`,
  then the hours containing them, then attribution and inference rollups for those hours.
  Running it twice gives the same result.
- **A watermark.** The rollup job (every 5 s, one replica at a time through
  `pg_try_advisory_xact_lock`) closes the minutes between the stored watermark and
  `now - ROLLUP_LAG_S` (90 s by default). Rows that arrive within the lag are included
  naturally.
- **Dirty ranges.** Ingest records `[oldest row, newest row + 1 s)` for a host in
  `rollup_dirty` when a batch holds rows older than **half** the lag. The next tick merges
  the queued ranges per host, recomputes them, and deletes them only afterwards.
- **The lag/2 rule.** Queuing rows older than half the lag, not the full lag, covers an
  ingest transaction that commits while the watermark is closing the range containing its
  rows. Some rows are rolled up twice, which is harmless; a row is missed only if an ingest
  transaction takes longer than half the lag (45 s by default).
- Recompute works in steps of 6 hours, each in its own transaction, so a long backfill
  never holds one huge transaction.

## Consequences

**Good**
- Late data is rolled up exactly once in effect, with no double counting
  (`test_late_samples_are_rolled_up_exactly_once`).
- Spool replays and backfills fix their own history without operator action.
- Safe with several worker replicas.
- Re-attribution after a rule change reuses the same mechanism (queue dirty ranges over the
  raw retention window).

**Bad / caveats**
- Buckets are final only after `ROLLUP_LAG_S`; the live view and raw-resolution charts
  cover the most recent minutes.
- A large backfill delays the watermark path while its ranges are recomputed.
- Retention must not drop raw partitions the watermark has not passed (it checks).

## Alternatives considered

- **Postgres materialized views.** Refresh is all or nothing.
- **Incremental counters on ingest.** Fast, but not idempotent under retries and replays.
- **TimescaleDB continuous aggregates.** Similar semantics, but an extension the stack does
  not otherwise need ([ADR-0001](0001-postgres-for-metrics.md)).

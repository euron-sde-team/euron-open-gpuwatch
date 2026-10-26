# ADR-0006: Redis is optional, with an in-process fallback

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

GPUWatch uses a key-value store for the live view (newest sample per GPU), the live
sequence the SSE stream watches, rate limit windows and the config cache version stamp. A
single-machine install (one workstation, a few GPUs) should not need another service, and
a Redis outage must never lose samples or let a revoked credential back in.

## Decision

- Every use goes through one small `KV` Protocol
  ([`core/kv.py`](../../../apps/api/src/gpuwatch/core/kv.py)) with two implementations:
  `RedisKV` (`REDIS_URL` set) and `MemoryKV` (empty `REDIS_URL`): a bounded LRU with
  expiry (20,000 entries, 64 MB) and fixed-window rate counters, exact for a single
  process.
- **Postgres is the source of truth.** Samples are committed before the live store is
  written. A KV error is treated as a miss or a pass and counted in
  `gpuwatch_dependency_errors_total`: the live view falls back to the newest stored sample,
  the SSE stream polls every 5 s, rate limits pass, the config cache expires on its 5 s
  TTL.
- **Security state never lives only in the KV store.** Signed-out sessions, session
  versions, lockout counters and token hashes are in Postgres.
- `/readyz` requires Postgres only and reports Redis as degraded.
- The integration suite runs under both backends (`make test-matrix`, `TEST_CACHE=memory`).

## Consequences

**Good**
- `REDIS_URL=` runs the whole stack without Redis.
- A Redis outage or eviction costs freshness and limits, never data
  (`allkeys-lru` locally; the AWS cache module's memory alarm warns first).
- One place to reason about every KV use.

**Bad / caveats**
- Without Redis, state is per process: with several API replicas (or `WEB_CONCURRENCY`
  above 1) the live view, rate limits and config invalidation are per process. Use Redis
  for more than one API process.
- The memory backend's rate limiter uses fixed windows (the Redis one is a sliding window),
  so limits are slightly less smooth at window edges.

## Alternatives considered

- **Redis required.** Simpler code, but a heavier install and a hard dependency for data
  that Postgres can rebuild.
- **Postgres for everything, including the live view.** Possible (the fallback does it),
  but every dashboard refresh would query raw samples.

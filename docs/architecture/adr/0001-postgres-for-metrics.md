# ADR-0001: Postgres for metrics, with a Prometheus exposition, instead of a Prometheus server

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

The source brief suggested Prometheus as the metrics store. GPUWatch needs raw GPU samples
every 5 s per GPU, history over months, and cost accounting that joins samples with
processes, workload rules and rates, and has to add up exactly. Many teams already run
Prometheus and Grafana and want to keep their dashboards.

Every Euron reference project faced the same choice and kept time series in Postgres:
SmartRouter and ContextForge keep hourly rollups there, TokenShield its budget windows,
the video system its usage service, and all of them expose Prometheus metrics with
`prometheus_client` without running a Prometheus server. On AWS, the managed Prometheus
equivalent (Amazon Managed Service for Prometheus) is not emulated by Floci, so it could
not be exercised locally, which the program rules require of every resource.

## Decision

Store everything in PostgreSQL 16: raw GPU and process samples in tables range-partitioned
by day, minute and hour rollups, hourly workload usage and hourly inference rollups.
Retention drops whole raw partitions after `RAW_RETENTION_DAYS` (once rolled up) and trims
rollups by age.

Expose `/metrics` in the Prometheus text format: GPUWatch's own counters and histograms,
plus one gauge per GPU and metric for the whole fleet, computed on scrape from the live
view. An existing Prometheus or Grafana scrapes GPUWatch instead of running its own
exporters on every machine. The endpoint is protected by `METRICS_TOKEN`.

## Consequences

**Good**
- One datastore to run, back up and secure.
- Exact cost attribution is SQL over the same store (samples, processes, rules, rates),
  inside one transaction per recompute.
- The AWS equivalent is plain RDS, already provisioned and exercised by `make tf-aws-on-floci`.
- Volume fits: at 5 s, 100 GPUs write about 1.7 million raw rows a day, kept 7 days, with
  rollups for longer ranges. Dashboards never scan raw rows for ranges over 3 hours.
- Prometheus users still get every GPU as a gauge.

**Bad / caveats**
- No PromQL over GPUWatch's own history. History queries are the API's, and Prometheus
  sees only what it scrapes from `/metrics` (current values).
- Write volume grows linearly with GPUs and interval; very large fleets need a larger RDS
  instance or a longer interval before they need a different store.
- Partition upkeep is GPUWatch's job (the worker creates them ahead, ingest on demand).

## Alternatives considered

- **Prometheus server (or Amazon Managed Prometheus) as the store.** Strong for metrics,
  weak for exact joins with processes and rates; another stateful service; not emulated
  locally.
- **TimescaleDB.** Hypertables and continuous aggregates would replace some code, but add
  an extension the RDS default does not offer and the references do not use.
- **ClickHouse.** Fast for analytics, another datastore to operate for a 0.1.0 volume
  that Postgres handles.

# ADR-0004: Exact cost attribution with a largest-remainder split per GPU-hour

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

The product promise is that every GPU-hour is accounted for: attributed to a workload or
marked idle, adding up exactly to the configured cost. Users group costs by workload,
team, host, GPU and model, and export CSVs for chargeback; if those totals disagree by a
nano-dollar, trust in every figure goes with it. Several processes often share a GPU, and
drivers report different things: SM share per process on most data centre cards, only
memory on some, nothing in some containers.

## Decision

Two stages ([cost-attribution.md](../cost-attribution.md)):

1. **Seconds, at rollup time.** Each sample's `interval_s` is split across the processes on
   the GPU at that sample, weighted by SM share when the driver reports it, else by VRAM,
   else equally. A sample with no process is idle, or `(unattributed)` when the GPU was
   busy (the driver lists no processes here). Seconds below the idle threshold are also
   recorded inside each workload as held idle time. Result: `workload_usage_1h`, whose
   rows add up per (GPU, hour) to the hour's monitored seconds.
2. **Money, at read time.** Per GPU-hour, the cost is computed once from the cell's
   seconds and the applied rate (GPU, then host, then model), as an integer number of
   nano-dollars, then split across the cell's rows by **largest remainder**: floors of the
   exact shares, with the leftover nano-dollars going to the largest fractional parts.
   Every grouping sums the same split amounts.

## Consequences

**Good**
- Workloads plus idle equal the GPU's cost exactly; all groupings and the series agree to
  the nano-dollar; tests use equality (acceptance criterion 5).
- Rate changes apply to the whole history without rewriting stored rows.
- Unpriced GPUs are visible (`unpriced_gpu_hours`) instead of silently free.
- Busy time on hosts without process listing is shown as unattributed, never as idle.

**Bad / caveats**
- Attribution needs raw samples: changed workload rules can be re-applied only as far back
  as raw retention (7 days by default); older hours keep their attribution.
- Held idle cost is a per-row rounded part (`round(amount * idle_s / s)`), so its total is
  exact to within rounding per row, not by construction.
- Per-sample splitting is only as good as the driver's process data; SM shares are sampled
  by NVML, not measured per instruction.
- Costs are computed per request from hourly usage; very long windows over large fleets
  cost CPU on the API.

## Alternatives considered

- **Store money per sample.** Fixes rates in time and makes rate corrections a migration.
- **Proportional floats, rounded at display.** Groupings would disagree in the last digit.
- **Attribute by process presence only (equal split).** Ignores the SM and memory data the
  driver gives, and misattributes shared GPUs.

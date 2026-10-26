# ADR-0002: Money as integer nano-dollars

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

GPUWatch prices every monitored GPU-second at an hourly rate and promises that workload
costs plus idle cost equal the GPU's cost exactly (acceptance criterion 5). A 5 s sample
on a USD 0.60 per hour card costs about USD 0.00083; floating point dollars accumulate
error across millions of such amounts, and cents are far too coarse.

## Decision

Every amount is an integer number of nano-dollars (1 USD = 10^9 nUSD) in a `BIGINT`
column or a Python `int` ([`core/money.py`](../../../apps/api/src/gpuwatch/core/money.py)):

- Rates are entered as decimal USD and converted once with `usd_to_nusd`, rounding up to
  the next nano-dollar.
- The cost of a GPU-hour is `round(seconds * nusd_per_hour / 3600)`, one rounding per
  GPU-hour, then split into integer parts by largest remainder
  ([ADR-0004](0004-exact-cost-attribution.md)).
- The API returns `*_nusd` integers; the dashboard and CSV exports format them as USD
  (CSV with six decimals from `Decimal`).

## Consequences

**Good**
- Sums are exact in every grouping; tests compare totals with `==`.
- A `BIGINT` holds about 9.2 billion USD in nano-dollars, far above any GPU bill.
- Sub-cent amounts (per-request inference cost, per-sample cost) stay meaningful.

**Bad / caveats**
- API consumers must divide by 10^9; field names say `nusd` to make that hard to miss.
- Rounding happens per GPU-hour, so the sum of hourly costs can differ from a single
  `seconds * rate` over a long window by up to half a nano-dollar per hour. GPUWatch
  defines the cost as the sum of hourly costs, consistently everywhere.
- One currency (USD). A rate in another currency must be entered as if it were USD.

## Alternatives considered

- **Floating point USD.** Simple, but totals drift and equality tests fail.
- **`NUMERIC` / `Decimal` everywhere.** Exact, but slower and easy to mix with floats at
  the boundaries; an integer unit is harder to misuse.
- **Micro-dollars.** Too coarse for per-sample amounts on cheap cards.

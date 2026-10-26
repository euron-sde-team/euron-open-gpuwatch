# Cost Attribution

Who used the GPU, and what it cost. The promise is acceptance criterion 5: for any window,
the sum of workload costs plus idle cost equals the GPU's cost to the nano-dollar. Code:
[`costs/attribution.py`](../../apps/api/src/gpuwatch/costs/attribution.py),
[`costs/rates.py`](../../apps/api/src/gpuwatch/costs/rates.py),
[`costs/service.py`](../../apps/api/src/gpuwatch/costs/service.py).

- [Two stages](#two-stages)
- [Stage 1: seconds per workload](#stage-1-seconds-per-workload)
- [Workload rules](#workload-rules)
- [Rates and precedence](#rates-and-precedence)
- [Exact pricing per GPU-hour](#exact-pricing-per-gpu-hour)
- [Why the totals agree to the nano-dollar](#why-the-totals-agree-to-the-nano-dollar)
- [Idle, held idle and unattributed](#idle-held-idle-and-unattributed)
- [Re-attribution](#re-attribution)
- [Tests](#tests)

## Two stages

1. **Seconds.** The rollup job turns raw samples and processes into
   `workload_usage_1h`: seconds per (GPU, hour, workload), with the part of those seconds
   spent idle. This depends on the workload rules and the idle threshold, not on prices.
2. **Money.** Every cost read (`GET /api/v1/costs`, the series, reports, the overview, the
   GPU explanation) prices those seconds with the rates in force at read time and splits
   each GPU-hour exactly.

Keeping money out of the stored rows means a rate change applies to the whole history at
once, and there is no stored amount that could drift from its inputs.

## Stage 1: seconds per workload

`attribute()` walks every sample of the hours being recomputed:

- The sample's hour is `ts` truncated to the hour. Its weight is its `interval_s`.
- The sample is **idle** when `util_gpu` is NULL or below `idle_util_pct` (5% by default,
  editable in Settings, Insight rules).
- The processes on the GPU at that sample are the `process_samples` rows with the same
  `(gpu_id, ts)`.

Then:

- **No process listed:** the whole interval goes to the idle bucket (workload `''`) when
  the sample is idle, and to `(unattributed)` when the GPU was busy. A busy GPU with no
  process means the driver does not list processes in this environment (some containers,
  vGPU, or the DCGM exporter collector), so the time is shown as unattributed, never
  silently as idle.
- **Processes listed:** the interval is split across them by weight:
  1. by **SM share** (`sm_util`) when the driver reported it for any process and the
     shares add up to more than zero;
  2. else by **VRAM** (`mem_used_mib`) when it adds up to more than zero;
  3. else **equally**.

  Each process maps to a workload and team through the workload rules (or, with no
  matching rule, to its process name truncated to 80 characters, with no team). When the
  sample was idle, the process's share is also added to that workload's `idle_seconds`:
  the workload held the GPU (typically a loaded model) without using it.

Invariant: per (GPU, hour), the workload rows' `seconds` add up to the sum of the
samples' `interval_s` in that hour. Every monitored second lands in exactly one bucket
(`test_seconds_add_up_per_gpu_hour`).

`recompute()` deletes the usage rows of the affected (GPU, hour) cells and inserts the new
ones in chunks of 2,000, inside the rollup transaction. Hours whose raw samples were
already dropped by retention keep their stored usage.

## Workload rules

A rule has a priority (lower first), a workload, an optional team, and any of: a process
name regular expression (searched, not anchored unless the pattern says so), a container
id prefix, a Unix user name, and a host label `key=value`. Every condition that is set must
match; the first matching enabled rule wins. Patterns are validated on write; a rule whose
pattern no longer compiles is skipped rather than breaking attribution.

The demo seeds rules such as `^python3?$` on hosts labelled `role=training` to
`llm-finetune` (team Research) and `vllm` to `llama-chat` (team Platform).

## Rates and precedence

GPUWatch ships no prices. A rate is an hourly amount in USD, stored as integer
nano-dollars (`usd_to_nusd` rounds up to the next nano-dollar), at one of three scopes:

| Scope | Applies to |
| ----- | ---------- |
| `gpu` | One GPU |
| `host` | Every GPU on one host |
| `model` | Every GPU whose driver-reported name equals the model string |

The most specific rate wins: the GPU's own, then its host's, then its model's
(`rates.pick`). Each target has at most one rate (partial unique indexes). A GPU with no
applicable rate is left out of every money total, and its hours are reported separately as
`unpriced_gpu_hours`, so a missing rate is visible instead of silently cheap.

## Exact pricing per GPU-hour

`allocations(start, end)` aligns the window to whole hours (at most 400 days) and reads
the usage rows in it. For each (GPU, hour) cell:

1. `seconds` = the sum of the cell's workload seconds.
2. `cost = round(seconds * nusd_per_hour / 3600)`: one rounding per GPU-hour, to the
   nearest nano-dollar.
3. `split(cost, [row.seconds for row in cell])` divides that integer across the cell's
   rows by **largest remainder**: each row gets the floor of its exact share, and the
   leftover nano-dollars go one each to the rows with the largest fractional parts (ties to
   the earlier row in a stable order). The parts are integers that add up to exactly
   `cost`.
4. For a workload row, its idle part is `round(amount * idle_seconds / seconds)`; for the
   idle bucket, the whole amount.

The result is a list of allocations `(gpu, hour, workload, team, seconds, nusd,
idle_nusd)`.

## Why the totals agree to the nano-dollar

- A GPU's cost over a window is defined as the sum of its GPU-hour costs (step 2).
- Each GPU-hour cost is split into integer parts that add up to it exactly (step 3).
- Every view (by workload, team, host, GPU or model, and the time series) is a grouping of
  the same allocation amounts. No view recomputes or re-rounds money.

So workloads plus idle equal the GPU's cost exactly, and the grand total is identical in
every grouping. Floating point appears only in the weights passed to the split, never in
an amount. Acceptance test `test_5_workload_costs_plus_idle_equal_gpu_cost_exactly`
checks it against the API; `test_split_is_exact_and_proportional` checks the split
property in unit tests.

## Idle, held idle and unattributed

A summary reports three kinds of time that bought nothing or cannot be named:

| Field | Meaning |
| ----- | ------- |
| `idle_nusd` | The idle bucket: GPU time with nothing running |
| `held_idle_nusd` | The idle part of workload rows: a workload held the GPU (processes listed) while utilization was below the threshold. Each row's part is rounded separately, so this figure is a rounded sum, not an exact split |
| `(unattributed)` row | Busy time on a GPU whose driver does not list processes |

The overview's "paid for idle time" is `idle_nusd + held_idle_nusd` over 7 days. In
groupings by team, the idle bucket shows as "Idle (nothing running)" and unattributed time
as "Unattributed (driver lists no processes)".

## Re-attribution

New or changed workload rules apply to hours rolled up from then on. To apply them to
recent history, an admin calls `POST /api/v1/workload-rules/apply` (Costs, Workload rules,
"Apply to recent history"). It queues one dirty range per host covering
`RAW_RETENTION_DAYS`; the next rollup ticks recompute those hours from raw samples. Older
hours, whose raw samples are gone, keep their attribution.

## Tests

| Behaviour | Test |
| --------- | ---- |
| Split is exact and proportional | `tests/unit/costs/test_attribution.py::test_split_is_exact_and_proportional` |
| SM share, then memory, then equal | `test_attribution.py::test_samples_split_by_sm_share_then_memory_then_equally` |
| Empty GPUs are idle unless busy | `test_attribution.py::test_empty_gpus_are_idle_unless_busy` |
| Held idle time is counted inside the workload | `test_attribution.py::test_held_idle_time_is_counted_inside_the_workload` |
| Seconds add up per GPU-hour | `test_attribution.py::test_seconds_add_up_per_gpu_hour` |
| Rules match on every set condition in priority order | `test_attribution.py::test_rules_match_on_every_set_condition_in_priority_order` |
| Rate precedence and cost rounding | `test_attribution.py::test_rate_precedence_and_cost`, `tests/unit/core/test_money.py` |
| Most specific rate first, against the API | `tests/integration/test_costs.py::test_rates_apply_most_specific_first` |
| Unpriced hours are reported | `test_costs.py::test_without_a_rate_hours_are_reported_unpriced` |
| Rules map processes and apply retroactively | `test_costs.py::test_workload_rules_map_processes_and_apply_retroactively` |
| A GPU without process listing is unattributed while busy | `tests/integration/test_telemetry.py::test_a_gpu_without_process_listing_is_unattributed_while_busy` |
| Workload costs plus idle equal GPU cost exactly | `tests/integration/test_acceptance.py::test_5_workload_costs_plus_idle_equal_gpu_cost_exactly` |
| Idle cost equals rate times idle hours | `test_acceptance.py::test_4_a_loaded_but_idle_gpu_costs_rate_times_idle_hours` |

# Walkthrough

A tour of every screen with the demo fleet (`make up && make demo`, sign in at
<http://localhost:4410> as `owner@gpuwatch.local` with the password from
`deploy/compose/.env`). The demo is three simulated hosts sending through the real ingest
API: `train-node-01` (8 x H100), `infer-node-01` (2 x L40S, 2 x L4, with vLLM and TGI
endpoints) and `dev-workstation` (1 x GeForce RTX 4090). Nothing on these screens is
hardcoded; the simulator follows the clock, so exact numbers and findings change over the
day.

The sidebar groups the screens: **Monitor** (Overview, Live, Hosts, Inference),
**Optimize** (Insights, Costs, Alerts) and **Organisation** (API keys, Users, Audit log,
Settings). Viewers do not see API keys, Users and Audit log. Every screen works in light
and dark mode and at phone width.

- [Sign in](#sign-in)
- [Overview](#overview)
- [Live](#live)
- [GPU detail](#gpu-detail)
- [Hosts](#hosts)
- [Inference](#inference)
- [Insights](#insights)
- [Costs](#costs)
- [Alerts](#alerts)
- [API keys](#api-keys)
- [Users](#users)
- [Audit log](#audit-log)
- [Settings](#settings)

## Sign in

Email and password. Wrong credentials say so; five failures lock the account for 15
minutes. A session expiry anywhere in the app shows one toast and returns you here,
keeping the page you were on.

## Overview

**What your GPUs cost, how much of it bought nothing, and what to look at first.**

- KPI tiles: **Spend, last 7 days**, **Paid for idle time** (nothing running plus
  workloads holding a GPU without using it), **Waste found, per month** (the estimates of
  open spend findings) and **GPUs reporting**.
- **Fleet, last 24 hours:** average utilization and memory across reporting GPUs, and
  their total power.
- **Cost by workload, last 7 days:** the top workloads, with the idle bucket as its own row.
- **Top findings:** the five most costly open findings, linking to Insights.

Why it matters: in the demo the training node's notebook GPUs and the spare L4 make the
idle share visible at a glance. Without rates, the cost tiles explain that costs appear
once a rate is set; without hosts, an empty state explains how to add the first one.

## Live

**Every GPU right now.** One tile per GPU (13 in the demo) with utilization, memory used
against the card's total, temperature, power and process count, grouped by host. Tiles
update as soon as an agent reports, every few seconds, pushed over server-sent events. The
header shows "Live", or "Refreshing every 5 s" when the stream is unavailable and the page
polls instead.

- Filter by **All**, **Busy**, **Idle** or **Problems**, and search by name.
- Simulated hosts carry a visible badge.
- Fields a GPU does not report read "Not available", never 0: the RTX 4090 has no ECC, and
  the passively cooled H100 and L4 have no fan speed.
- Lost and offline GPUs are marked as such.

Click a tile for the GPU page.

## GPU detail

Everything about one GPU, with a range selector (1h, 6h, 24h, 7d, 30d; raw samples up to
3 hours, minute rollups up to 3 days, hours beyond).

- **The explanation card:** "why is this GPU expensive or slow" in a few sentences: what
  it cost over the insight window and for which workloads, how much paid for idle time,
  throttling, memory pressure or errors. For a notebook H100 in the demo the headline
  reads "Expensive because it sits idle N% of the time".
- **This GPU:** the newest reading (utilization, memory of the card's total, temperature,
  power of its limit, fan, SM clock, PCIe in and out, uncorrected ECC errors, throttle
  reasons right now, each "Not available" when not reported), the applied rate and its
  scope, the UUID, PCI bus, MIG mode and when it was first seen.
- **Utilization, Memory, Temperature and power, Clocks and throttling:** history charts.
  The throttling chart shows the share of busy time slowed down by power, thermal and
  hardware reasons; a GPU that reports no throttle reasons says so instead of drawing 0.
- **Processes and workloads:** the processes on the GPU now (pid, name, user, container,
  memory, SM share, the workload and team they map to) and who used it over the last day,
  including idle and unattributed time.
- **Findings for this GPU:** its open insights.
- Admins can **Retire** a GPU that shows as lost (and restore it).

## Hosts

**Machines running the GPUWatch agent.** Each host shows its status (online,
disconnected, pending, revoked), agent status (ok or degraded with the reasons), GPU count,
labels, agent version, collector, driver and CUDA versions, interval and last seen time.

- **Add a host** creates an enrolment token (shown once) and prints the install command
  for Docker, pip or DCGM exporter mode with your URL and token filled in. The new host
  appears within seconds of the agent starting.
- **Edit** renames a host or changes its labels; **Revoke** stops accepting its data
  (history stays).
- **Enrolment tokens:** every token with its labels, expiry, uses and whether it is still
  usable; revoke one to stop new enrolments.

## Inference

**Serving metrics from vLLM and TGI next to the GPUs they run on, with cost per million
tokens.** The demo has `llama-chat` (vLLM on an L40S) and `summarizer` (TGI on an L40S).

- Per endpoint, last 24 hours: requests per second, generated tokens per second, TTFT and
  inter-token latency p50 and p95, end-to-end p95, running and waiting requests, KV cache
  use, GPU utilization, cost per million tokens and per request. TGI exposes no TTFT and
  no KV cache, which read "Not available".
- Charts over a chosen range (1h, 6h, 24h, 7d): **Throughput**, **Latency**, **Queue** and
  **KV cache**. At the chat model's daily peak the queue and KV cache charts show requests
  waiting with the cache nearly full, which is what the queueing finding reports.

## Insights

**Why your GPUs are expensive or slow, ranked by what they cost.** Tabs for **Open**,
**Acknowledged**, **Dismissed** and **Resolved**; the open tab shows what the open findings
cost a month in total.

Each card shows the finding, its severity, the GPU or endpoint, the window, the estimated
monthly cost where there is one, the summary with the evidence behind it (idle periods,
throttle shares, peak memory, a cheaper card from your own rates) and the recommendation.
Admins can acknowledge, dismiss or reopen; findings resolve by themselves when the
condition clears. "Check now" re-runs the engine; "Rules" opens the thresholds in Settings.

Typical demo findings: notebook H100s idle with a model loaded, the spare L4 with nothing
running, oversized VRAM on the notebook GPUs and the summarizer's card, the workstation
slowed by its power cap, an H100 slowed by its thermal limit, an XID on another H100,
queueing on `llama-chat`, and the summarizer serving at low GPU utilization.

## Costs

**What GPU time cost, and how much of it bought nothing.** Figures are estimates from your
own hourly rates. Four tabs:

- **Breakdown:** group by workload, team, host, GPU or model over 24h, 7d or 30d. Tiles
  for total cost, idle with nothing running, held idle by workloads and GPU hours; a
  stacked cost-over-time chart; a table with each row's cost, idle share, GPU hours and
  share of the total. Every grouping adds up to the same total, to the nano-dollar. A
  warning lists GPU hours without a rate.
- **Rates:** hourly rates per GPU model, host or GPU, with how many GPUs each covers. The
  most specific rate wins. The demo's four model rates are labelled as examples.
- **Workload rules:** map processes to workloads and teams by name pattern, container id
  prefix, user or host label, in priority order. **Apply to recent history** re-attributes
  the hours that still have raw samples.
- **Reports:** export a CSV of cost, idle cost and GPU hours per group for a period; every
  export is kept for download by anyone on the team.

## Alerts

**Rules watch every GPU and host; channels get a message once when one fires and again
when it resolves.** Four tabs:

- **Events:** firing first, then recent resolved ones, with the rule, target, value and
  duration.
- **Rules:** the built-in rules (agent offline, GPU lost, GPU too hot, GPU memory almost
  full) plus the demo's "Training GPU too hot" (scoped to `role=training`). Add a rule on
  any metric with an operator, threshold, duration, scope, severity and channels; pause or
  delete rules.
- **Channels:** email addresses and webhooks. The demo's "Ops on-call email" lands in
  Mailpit (<http://localhost:4425>). Webhooks take an optional signing secret (stored
  sealed, never shown again). **Send test** delivers a test notification.
- **Deliveries:** every notification sent or still being retried, with attempts and the
  last error.

## API keys

Read-only `gwk_` keys for scripts and dashboards: GPUs, history, costs, insights and
alerts over the REST API. Create a key (shown once) with an optional rate limit and expiry,
edit its name, limit or expiry, or revoke it. Each key shows when it was last used. The
demo creates "Grafana (read only)". Admins and owners only.

## Users

People who can sign in. Owners add users with a role (owner, admin, viewer) and an
initial password, change roles and disable access; at least one active owner always
remains. Admins can see the list.

## Audit log

Every configuration change and sign-in, append-only: who did what, to which object, from
which address, with details. Filter by action. Agent enrolments appear with the actor
"agent". Admins and owners only.

## Settings

- **System:** how this install is configured, read from the running API (environment,
  cloud, webhook secret sealing, report storage, live view and rate limit backend, alert
  email mode, dashboard URL, agent offline threshold, retention, active API keys).
  Changed through environment variables.
- **Insight rules:** the idle rule and every insight threshold, editable by admins. They
  apply to every GPU on the next evaluation (and the idle threshold to cost attribution).
- **Appearance:** light, dark or system theme, saved in this browser.
- **Your account:** change your password; other sessions are signed out.

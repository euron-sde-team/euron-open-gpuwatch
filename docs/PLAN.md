# Euron Open GPUWatch 0.1.0: build plan

**Why is my GPU expensive or slow, and what can I do about it?** A self-hosted GPU
monitoring and cost intelligence platform: a small agent collects metrics from NVIDIA GPUs
(NVML, or an existing DCGM exporter) on each machine, the API stores and analyses them, and
the dashboard answers with evidence: which workloads used the GPU, how much of the spend
was idle, what is throttling it, and what to change.

Source brief: "Euron GPUWatch" (`briefs/04-gpuwatch.md`). Where the brief and the repository
rules differ, the rules win: MIT instead of Apache 2.0, repo `euron-open-gpuwatch`, Next.js
dashboard, `apps/api` layout, Docker plus Terraform plus Floci.

## Purpose

ML engineers, startups serving models and platform teams pay for GPUs by the hour, but the
tools they have show a percentage, not an answer. `nvidia-smi` and nvtop show this second on
one machine. DCGM exporter plus Prometheus plus Grafana gives history, but someone has to
build it, and it still shows "23% utilization" without saying that the A100 held a loaded
model with no traffic for 14 hours last night, which cost real money, or that the inference
box is slow because it is power-capped. **A watch must keep watching and raise its hand, so
GPUWatch must continuously record every GPU it can reach, tell unavailable from zero, notice
idle and wasted spend without being asked, explain slowness from the driver's own throttle
reasons, and alert someone before a GPU runs out of memory or goes dark.** The outcome it
guarantees: every GPU-hour is accounted for (attributed to a workload or marked idle, adding
up exactly to the configured cost), every finding carries the evidence behind it, and
nothing is changed on the machine: GPUWatch observes and recommends, it never kills or
starts a process.

### Comparable products (researched October 2026)

| Product | What it is | Gap GPUWatch fills |
| --- | --- | --- |
| nvidia-smi, nvtop, nvitop (Apache 2.0) | Terminal monitors for one machine, nvitop with a Prometheus exporter | No fleet, no history without extra stack, no cost, no findings |
| NVIDIA DCGM exporter + Prometheus + Grafana dashboards | The standard metrics pipeline | Raw metrics only; idle detection, attribution and cost are left to you as PromQL |
| Datadog GPU Monitoring, cloud vendor consoles | Commercial, cost and usage views | SaaS, per-host pricing, metrics leave your network |
| Run:ai, Kubernetes GPU schedulers | Allocation and quotas on Kubernetes | Heavy, cluster-only, not a monitor for a workstation or a few VMs |

What makes ours worth starring: install in one command, works without a GPU in demo mode,
an insights engine that turns metrics into ranked findings with an estimated monthly cost,
exact cost attribution per workload, and inference metrics (TTFT, tokens per second, cost
per million tokens) next to the GPU they run on. GPUWatch reuses proven collection (NVML,
DCGM exporter output, vLLM and TGI Prometheus endpoints) rather than inventing telemetry.

## Acceptance criteria (each is an automated test)

1. **Live:** a sample collected by an agent appears on the dashboard's live view within 5 s
   (e2e, simulated agent through the real ingest path).
2. **Unavailable is not zero:** a metric the driver reports as not supported is stored as
   null and shown as "Not available", never 0, in the API and the UI (integration + e2e).
3. **Disconnected:** an agent that stops reporting marks its host disconnected within 90 s
   and raises one "agent offline" alert, resolved when it returns (integration).
4. **Idle spend:** a GPU holding VRAM below 5% utilization for the configured window yields
   an "idle with a model loaded" finding whose cost equals rate times idle hours (integration,
   exact arithmetic).
5. **Exact attribution:** for any window, the sum of workload costs plus idle cost equals
   the GPU's cost to the nano-dollar (integration, property test in unit).
6. **Alerts:** temperature above threshold for the rule's duration fires exactly one alert,
   delivered by email (Mailpit) and an HMAC-signed webhook, and resolves exactly once
   (integration).
7. **No lost data:** an agent buffers while the API is down and replays afterwards with no
   duplicate samples (integration).
8. **Slow explained:** throttle reason bits (power cap, thermal, hardware slowdown) during
   busy time produce a "throttled" finding naming the reason (integration).
9. **Inference cost:** vLLM metrics produce TTFT p95, tokens per second and cost per million
   tokens matching a hand calculation (integration against a mock vLLM).
10. **Driver failure is graceful:** NVML init failure or a driver error leaves the agent
    running and reporting a degraded status with the reason, shown on the host (unit +
    integration).
11. **Observe only:** the agent has no inbound port and no command channel; no API route can
    start or stop a process (unit test over the route table and agent code).
12. **Private by default:** nothing contacts a host outside the configured API and the
    machines' own endpoints; no telemetry (unit test over settings and outbound clients).

## Scope

### In 0.1.0

- **Agent** (`apps/agent`, Python, uv, one container or a pip install): collectors behind
  one Protocol: `nvml` (nvidia-ml-py), `dcgm` (reads an existing DCGM exporter endpoint),
  `simulated` (scenario driven, demo and tests). Per sample: utilization (GPU, memory),
  VRAM used and total, temperature, power draw and limit, fan, SM and memory clocks,
  throttle reasons, PCIe throughput, ECC errors, performance state; each nullable. Processes
  per GPU: pid, name, user, container id (from cgroups), VRAM, SM share where the driver
  gives it. Inference scrapers for vLLM and TGI `/metrics`. Batches posted every 5 s with a
  batch id (idempotent); disk spool and replay when the API is down; backoff; health and
  degraded reasons reported. No inbound port.
- **Hosts and enrolment:** an admin creates an enrolment token; the agent exchanges it for a
  host token (hashed at rest, revocable); labels; agent, driver and CUDA versions.
- **Live view:** latest sample per GPU in Redis, pushed to the dashboard by SSE.
- **History:** raw samples in a daily-partitioned Postgres table (7 days), 1-minute rollups
  (30 days) and hourly rollups (13 months), all retention configurable; charts by GPU, host,
  label, with spike and idle bands.
- **Cost:** hourly rate per GPU model, overridable per host or GPU; no built-in prices (the
  dashboard asks for a rate, the demo seeds example rates labelled as such). Money as
  integer nano-dollars.
- **Attribution:** each sample's cost split across workloads by SM share, falling back to
  VRAM share, else equal; time with no work is the idle bucket. Workload rules map process
  name, container or label to a workload and team.
- **Insights engine:** ranked findings with evidence, window and estimated monthly cost:
  idle with a model loaded, fully idle, underused (low average when busy), oversized VRAM
  (peak far below capacity), throttled (by reason), memory pressure (OOM risk), errors
  (ECC, XID where available), inference queueing with KV cache full, inference
  overprovisioned. Acknowledge, dismiss, auto-resolve. "Explain this GPU" summary sentence.
- **Alerts:** rules on any metric with operator, threshold, duration, scope (all, host, GPU,
  label), severity; built-ins for agent offline and GPU lost. Channels: email (SES, Mailpit
  locally) and webhooks (HMAC-signed, SSRF-checked URLs, retries through an outbox).
- **Inference module** (separate package and screens): endpoints bound to a GPU; requests per
  second, prompt and generated tokens, TTFT and inter-token latency percentiles from
  histograms, queue depth, KV cache use, cost per million tokens and per request.
- **Reports:** CSV cost and usage export by workload, team, host or GPU, stored in S3 (or local
  disk) and downloaded through the API, so access stays role-checked and audited.
- **Platform:** users with owner, admin and viewer roles, signed sessions with revocation in Postgres, CSRF, audit
  log, read-only API keys for the REST API, `/metrics` Prometheus exposition of the fleet
  (so an existing Prometheus or Grafana can scrape GPUWatch), OpenAPI documented.
- **Demo mode:** `make demo` starts simulated agents for a realistic fleet (a training node,
  an inference node running a mock vLLM, a developer workstation) that send through the real
  ingest path, plus 30 days of history generated by the same simulator. Simulated hosts carry
  a visible badge. No hardcoded numbers in the UI.

### Roadmap (not 0.1.0)

Kubernetes DaemonSet and pod or namespace attribution, AMD (ROCm SMI) and other collectors,
MIG instance level metrics, opt-in remediation actions with explicit authorization, SSO,
team budgets, Prometheus remote write, linking inference cost into SmartRouter's model
prices.

## Design

### Pipeline

agent collectors -> batch (5 s, idempotent id) -> `POST /ingest/v1/batches` (host token,
size and rate limited) -> Postgres raw partition + Redis latest + SSE fan-out -> worker:
1-minute and hourly rollups, attribution, insight evaluation (every minute, windows from
rollups), alert evaluation (every 15 s on latest values), offline detection, notification
outbox, retention (drop old partitions).

### Storage decision

The brief suggests Prometheus for metrics. Decision (2026-10-26, after checking the
references): **Postgres for everything** (partitioned raw samples plus rollups), and GPUWatch
exposes `/metrics` so Prometheus users can still scrape it. Every reference repo does the
same: SmartRouter and ContextForge keep hourly rollups in Postgres, TokenShield its budget
windows, the video system its usage service, and all of them expose Prometheus metrics with
`prometheus_client` without running a Prometheus server. Further reasons: one datastore to
run and back up, exact cost accounting needs SQL joins with
rates and workloads, AWS equivalent is plain RDS (Amazon Managed Prometheus is not emulated
by Floci, so it could not be tested locally), and volume fits (100 GPUs at 5 s is about
1.7 M raw rows a day, kept 7 days, with rollups for longer).

### Trust boundary

Agents are untrusted input: hashed host tokens, per-host rate limits, body size limits in
ASGI middleware (chunked bodies counted), strict schemas, timestamps clamped to a skew
window (demo backfill only for hosts marked simulated). Webhook URLs SSRF-checked, secrets
sealed with KMS. Security state (sessions, revocations) in Postgres, never an evictable cache.

### Caching layers

Redis latest sample per GPU (hot read, overwritten on ingest), SSE fan-out by pub/sub,
in-process config cache (rates, rules, workloads) invalidated cluster-wide by a version key,
React Query staleTime per view. Documented in HLD.md with invalidation tests.

### Data model (Postgres)

users, sessions, api_keys, audit_log; hosts, enrolment_tokens, gpus; gpu_samples
(partitioned by day), gpu_rollups_1m, gpu_rollups_1h; process_samples, workload_rules,
workload_usage_1h; gpu_rates; insights; alert_rules, alert_events, channels,
notification_outbox; inference_endpoints, inference_rollups_1m; reports; settings.

### API surface

`/ingest/v1/*` (agents), `/api/v1/{hosts,gpus,metrics,processes,workloads,costs,insights,
alerts,channels,inference,reports,users,keys,audit,settings}`, `/api/v1/live` (SSE),
`/metrics`, `/healthz`, `/readyz`.

### Screens

Overview (fleet health, spend this month, idle share, top findings), Live (all GPUs, tiles),
GPU detail (charts, processes, throttle timeline, explain card), Hosts (enrolment, agent
status), Workloads and costs, Insights, Alerts (rules, events, channels), Inference, Reports,
Settings (rates, retention, users, keys, audit). Light and dark, phone width.

### Terraform modules

network, database (RDS), cache (ElastiCache), storage (S3 reports), kms, secrets, email (SES),
ecr, service (ECS Fargate: api, worker, web behind an ALB), observability (CloudWatch,
alarms on ingest errors and offline hosts). Agents run on the GPU machines themselves, so
they are documented, not deployed by Terraform.

## Ports (project 04)

web 4410, api 4430, postgres 4442, redis 4479, mailpit 4425, floci 4466, mock vLLM 4450,
tf-aws-on-floci 4496.

## Test plan

Static, unit (API and agent, 85%+), integration against Postgres, Redis and Floci (every
acceptance criterion, every endpoint, auth and roles, dependency down), test matrix (keys
local or KMS, storage local or S3), OpenAPI drift, Playwright e2e on `make up && make demo`,
Terraform validate, tflint, checkov and `tf-aws-on-floci`, sanitize, Puppeteer QA in light
and dark at desktop and phone width.

### Honest labelling

There is no NVIDIA GPU on the build machine. The NVML collector is tested against a fake NVML
module that reproduces the library's behaviour (not-supported errors, driver errors, MIG,
lost GPUs); the DCGM collector against recorded exporter output. The README states this and
lists the compatibility matrix as "tested with simulated hardware" until a real GPU run is
done (`make agent-check` on a GPU machine prints what was collected). Cost figures are
estimates from user-configured rates, never claimed savings.

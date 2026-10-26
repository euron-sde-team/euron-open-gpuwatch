# Low-Level Design

How the code is laid out and how the important algorithms work, with pointers to the files.
The system view is in [HLD.md](HLD.md); the tables are in [data-model.md](data-model.md).

- [Repository layout](#repository-layout)
- [API package layout](#api-package-layout)
- [Request handling](#request-handling)
- [Domains](#domains)
- [Worker](#worker)
- [The agent](#the-agent)
- [The dashboard](#the-dashboard)
- [Important algorithms at a glance](#important-algorithms-at-a-glance)

## Repository layout

```
apps/api/      FastAPI service, worker and CLI: package gpuwatch (src/gpuwatch), tests/unit, tests/integration
apps/agent/    the agent: package gpuwatch_agent (collectors, inference scraping, spool, simulator, mock vLLM)
apps/web/      Next.js 15 dashboard (src/app routes, src/features/<domain>, src/lib)
e2e/           Playwright suites against make up && make demo
infra/         Dockerfiles (api, web, agent) and Terraform (modules, envs/local-floci, aws-dev, aws-prod)
deploy/compose compose.yaml plus the floci and aws overlays
scripts/       sanitization, env generation, test database, test matrix, tf-aws-on-floci, AWS deploy, qa/
docs/          architecture, guides, api/openapi.yaml (drift tested)
examples/      small scripts against the REST API and the webhook contract
```

## API package layout

Package by domain. Each domain owns its `router.py` (HTTP only), `schemas.py` (the public
contract), `service.py` (rules) and `models.py` (tables). A domain calls another domain's
service, never its router.

```
apps/api/src/gpuwatch/
  core/           config.py (Settings and boot guards), db.py (engine, Base), kv.py (Redis or
                  memory KV), cache.py (ConfigCache), security.py (passwords, sessions, tokens),
                  sealing.py (KeySealer: local AES-GCM or KMS), storage.py (ObjectStorage: local
                  or S3), mail.py (MailSender: log, SMTP, SES), aws.py (boto3 from config only),
                  middleware.py (request id, security headers, body limit), errors.py (one error
                  envelope), logs.py, tracing.py, money.py, schemas.py, container.py, deps.py
  ingest/         the agent contract: dependencies.py (host token auth, rate limit), schemas.py
                  (Batch, EnrolIn), service.py (store one batch), router.py (/ingest/v1/*)
  fleet/          enrolment tokens, enrolment, hosts, GPUs, derived status
  telemetry/      models.py (raw samples, rollups, batch ids, dirty ranges, job state),
                  partitions.py, rollups.py, retention.py, live.py, service.py (history queries),
                  router.py (metrics, processes, fleet series, live, live/stream)
  costs/          models.py, rates.py (precedence), attribution.py (who used the GPU),
                  service.py (rates, rules, exact summaries, series, reports)
  insights/       settings.py (thresholds), engine.py (pure rules), service.py (evaluate, store,
                  lifecycle, explain)
  alerts/         models.py, evaluator.py (stateless evaluation), notifier.py (outbox, signing),
                  urls.py (SSRF checks), service.py (rules, channels, events)
  inference/      models.py, histograms.py (merge, quantile), rollups.py, service.py (stats, series)
  auth/ users/ keys/ audit/    sessions and roles, users, read-only API keys, append-only audit
  overview/       the home screen in one call
  system/         /healthz, /readyz, /metrics, /api/v1/system
  observability/  metrics.py (Prometheus counters), fleet.py (per-GPU gauges on scrape)
  limits/         limiter.py (sliding-window rate limiter in Redis)
  demo/seed.py    demo configuration (refuses ENVIRONMENT=production)
  migrations/     Alembic env, runner, versions/0001_initial_schema.py
  main.py         create_app(): routers, middleware, lifespan
  worker.py       the job scheduler
  cli.py          gpuwatch serve | worker | migrate | revision | openapi | create-owner | seed-demo
  bench.py        make bench
  openapi.py      the exported document (docs/api/openapi.yaml)
```

## Request handling

Middleware order (outermost first), from [`main.py`](../../apps/api/src/gpuwatch/main.py):

1. `RequestContextMiddleware` ([`core/middleware.py`](../../apps/api/src/gpuwatch/core/middleware.py)):
   accepts or generates `X-Request-Id`, adds security headers, logs one line per request
   (quiet for `/healthz`, `/readyz`, `/metrics` and `/ingest/v1/batches` unless the status
   is 400 or more).
2. `BodySizeLimitMiddleware`: refuses bodies over `MAX_BODY_BYTES` with 413, checking
   `Content-Length` first and counting chunked bodies as they arrive; parses JSON bodies
   with orjson and refuses invalid UTF-8 or a lone surrogate with 422 `invalid_json`; then
   replays the buffered body to the app.
3. CORS (allowlist from `CORS_ORIGINS`), then gzip for responses of 2 KB or more.

Dependencies do the rest: `ContainerDep` (process-wide services built in the lifespan),
`SessionDep` (one `AsyncSession` per request), `AgentHostDep` for `/ingest/v1/batches`, and
`Viewer`, `Admin`, `Owner` for `/api/v1/*`. Errors are raised as typed `AppError`
subclasses and rendered once as `{"error": {"code", "type", "message", "details"}}`
([`core/errors.py`](../../apps/api/src/gpuwatch/core/errors.py)); an `IntegrityError` from a
race becomes 409, an expired report object 410, anything unhandled a logged 500 without a
stack trace in the body.

The `Container` ([`core/container.py`](../../apps/api/src/gpuwatch/core/container.py)) holds
the database, the KV store, the webhook HTTP client (redirects never followed), the config
cache, the sealer, the storage and the mail sender. Each backend is chosen by config
(`REDIS_URL`, `KEY_MODE`, `STORAGE`, `MAIL_MODE`); there are no emulator branches.

## Domains

### ingest

- [`dependencies.py`](../../apps/api/src/gpuwatch/ingest/dependencies.py): parses
  `Authorization: Bearer gwh_<prefix>_<secret>`, loads the host by prefix through the
  config cache, compares the peppered HMAC in constant time, refuses revoked hosts with
  `host_revoked`, then charges the per-host limiter (`ingest:<host id>`).
- [`schemas.py`](../../apps/api/src/gpuwatch/ingest/schemas.py): every field bounded,
  every metric optional (`None` is "not reported").
- [`service.py`](../../apps/api/src/gpuwatch/ingest/service.py): `store()` is described
  step by step in [ingest-and-rollups.md](ingest-and-rollups.md#storing-a-batch).

### fleet

[`service.py`](../../apps/api/src/gpuwatch/fleet/service.py)

- `create_token()` generates `gwe_<12 hex>_<secret>`, stores the prefix and the HMAC, and
  returns the plaintext once. Tokens can expire and have a use limit.
- `enrol()` locks the token row (`FOR UPDATE`), checks it, then creates the host or, for a
  known `machine_id`, keeps the host and its history and rotates its token. Labels merge
  token labels and agent labels. The host inherits `simulated` from the token. The config
  cache is invalidated so the old host token stops working immediately.
- Status is derived on read, never stored: `host_status()` (pending, online,
  disconnected, revoked) from `last_seen_at` and `HOST_OFFLINE_AFTER_S`; `gpu_status()`
  (ok, lost, offline, retired) from the GPU's and the host's last-seen times with a grace
  of `max(30 s, 3 x interval)`.
- `list_gpus()` joins GPUs, hosts, applied rates and the live store in a fixed number of
  queries (one `MGET` for every live sample) regardless of fleet size.

### telemetry

- [`partitions.py`](../../apps/api/src/gpuwatch/telemetry/partitions.py): daily range
  partitions of `gpu_samples` and `process_samples`, created under an advisory lock and
  memoised per process; dropped whole by retention.
- [`rollups.py`](../../apps/api/src/gpuwatch/telemetry/rollups.py): `tick()` and
  `recompute()`; see [ingest-and-rollups.md](ingest-and-rollups.md#rollups).
- [`live.py`](../../apps/api/src/gpuwatch/telemetry/live.py): `publish()`, `sequence()`,
  `latest()` (KV `MGET`, Postgres fallback).
- [`service.py`](../../apps/api/src/gpuwatch/telemetry/service.py): `resolution_for()`
  (raw up to 3 h, 1 m up to 3 days, 1 h beyond), `gpu_series()`, `fleet_series()` (per GPU
  and bucket first, then across GPUs, so a GPU that reported more often is not weighted
  more), `gpu_processes()` (processes at the newest sample, classified by the workload
  rules, plus workload shares over a window).
- [`router.py`](../../apps/api/src/gpuwatch/telemetry/router.py): `/api/v1/live/stream`
  is a `StreamingResponse` generator that polls `gw:live:seq` every second and yields a
  `snapshot` event when it changed, a heartbeat comment every 15 s otherwise.

### costs

- [`rates.py`](../../apps/api/src/gpuwatch/costs/rates.py): `pick()` applies GPU, then
  host, then model rates; `seconds_cost()` rounds to the nearest nano-dollar.
- [`attribution.py`](../../apps/api/src/gpuwatch/costs/attribution.py): `attribute()`
  turns samples and processes into seconds per (GPU, hour, workload); `recompute()`
  rewrites `workload_usage_1h` for whole hours from raw rows.
- [`service.py`](../../apps/api/src/gpuwatch/costs/service.py): `split()` (largest
  remainder), `allocations()` (every priced GPU-hour split exactly), `summary()` and
  `series()` (groupings over the same allocations), `reattribute()` (queues a dirty range
  per host over the raw retention window), `create_report()` (CSV to object storage, row
  keeps only the key).

The algorithm and its exactness argument are in [cost-attribution.md](cost-attribution.md).

### insights

- [`settings.py`](../../apps/api/src/gpuwatch/insights/settings.py): `InsightSettings`,
  stored as one JSON document in `app_settings` under `insights`; missing keys fall back
  to defaults, so a new setting needs no migration.
- [`engine.py`](../../apps/api/src/gpuwatch/insights/engine.py): pure functions over
  `Minute` rows (no database, no clock), one per rule.
- [`service.py`](../../apps/api/src/gpuwatch/insights/service.py): `evaluate()` loads
  minute rollups for the window in one query, idle holders and model rates, runs the
  engine per GPU and per inference endpoint, and `_store()` upserts by fingerprint and
  resolves what was not reported. `explain()` builds the "why is this GPU expensive or
  slow" sentences from the cost allocations and open findings.

Every rule and threshold is in [insights.md](insights.md).

### alerts

- [`evaluator.py`](../../apps/api/src/gpuwatch/alerts/evaluator.py): `evaluate()` per
  rule kind; one aggregate SQL query per threshold rule over raw samples of every GPU in
  scope; `_fire()` inserts with `ON CONFLICT DO NOTHING` on the partial unique index;
  `_resolve()` updates only an unresolved row.
- [`notifier.py`](../../apps/api/src/gpuwatch/alerts/notifier.py): `deliver_pending()`,
  `signature()`, `backoff()`, `email_text()`.
- [`urls.py`](../../apps/api/src/gpuwatch/alerts/urls.py): `check_webhook_url()`.
- [`service.py`](../../apps/api/src/gpuwatch/alerts/service.py): rule and channel CRUD;
  a webhook secret is sealed with the context `channel:<channel id>` before it is stored;
  test notifications go through the same outbox.

Details in [alerts.md](alerts.md).

### inference

- [`histograms.py`](../../apps/api/src/gpuwatch/inference/histograms.py): `merge()` sums
  non-cumulative bucket maps exactly; `quantile()` uses the same linear interpolation as
  PromQL's `histogram_quantile`, returning the last finite bound for the open bucket.
- [`rollups.py`](../../apps/api/src/gpuwatch/inference/rollups.py): hourly rollups from
  per-interval samples (sums for counters, interval-weighted averages for gauges, merged
  histograms).
- [`service.py`](../../apps/api/src/gpuwatch/inference/service.py): `stats()` computes
  requests per second, tokens per second, TTFT, inter-token and end-to-end p50 and p95,
  and cost per million tokens and per request; `gpu_usage()` prices the endpoint's bound
  GPUs over the window from minute rollups. Raw samples serve ranges up to 2 days, hourly
  rollups beyond. With no rate on any bound GPU, or no GPU bound, the cost fields are null.

### auth, users, keys, audit

- [`auth/dependencies.py`](../../apps/api/src/gpuwatch/auth/dependencies.py):
  `current_user()` (Bearer header first, then the `gw_session` cookie; revocation and
  `session_version` checks; CSRF header for cookie mutations), `current_actor()` (a `gwk_`
  key acts as a viewer on safe methods only), `require_role()`.
- [`auth/service.py`](../../apps/api/src/gpuwatch/auth/service.py): Argon2 verification off
  the event loop, a dummy hash for unknown emails, an atomic failure counter and a 15
  minute lockout after 5 failures; a password change bumps `session_version`.
- [`users/service.py`](../../apps/api/src/gpuwatch/users/service.py): at least one active
  owner, enforced by locking the owner rows during the check.
- [`keys/dependencies.py`](../../apps/api/src/gpuwatch/keys/dependencies.py): key lookup
  through the config cache, per-key rate limit, `last_used_at` written at most once a
  minute.
- [`audit/service.py`](../../apps/api/src/gpuwatch/audit/service.py): `audit()` adds a row
  in the same transaction as the change; `list_entries()` is keyset-paginated on id.

### system and observability

- [`system/router.py`](../../apps/api/src/gpuwatch/system/router.py): `/readyz` probes
  Postgres (required) and Redis (reported); `/metrics` checks `METRICS_TOKEN` when set and
  appends the fleet exposition from
  [`observability/fleet.py`](../../apps/api/src/gpuwatch/observability/fleet.py).

## Worker

[`worker.py`](../../apps/api/src/gpuwatch/worker.py) builds its own container, starts the
Prometheus HTTP server on `WORKER_METRICS_PORT`, and loops: `run_due()` runs each `Job`
whose `every_s` has elapsed since its last start, catching and counting failures. The job
table and the coordination of each job are in [HLD.md](HLD.md#worker-jobs).

## The agent

```
apps/agent/src/gpuwatch_agent/
  config.py     AgentConfig.from_env(): every GPUWATCH_* variable, parse_inference(), parse_labels()
  agent.py      Agent: enrol, collect, batch, deliver (spool on failure), replay, backfill, run
  client.py     the only network client: POST /ingest/v1/enroll and /ingest/v1/batches
  spool.py      disk spool: one JSON file per batch, atomic rename, bounded, oldest first
  collectors/   Collector Protocol; nvml.py, dcgm.py, simulated.py
  procinfo.py   process name, user and container id from /proc
  inference.py  vLLM and TGI /metrics to per-interval deltas
  promtext.py   a small Prometheus text-format parser
  model.py      Reading, GpuInfo, GpuSample, ProcessSample, Problem
  sim.py        deterministic scenarios (training, inference, workstation)
  mockvllm.py   a vLLM and TGI compatible /metrics server for the demo and tests
  cli.py        gpuwatch-agent run | check
```

Details in [agent.md](agent.md).

## The dashboard

`apps/web/src/app/` holds thin routes; each screen lives in `features/<domain>/`
(`overview`, `live`, `fleet` for hosts and GPU detail, `inference`, `insights`, `costs`,
`alerts`, `keys`, `users`, `audit`, `settings`, `auth`) with an `api.ts` of TanStack Query
hooks and its components. `lib/api/schema.d.ts` is generated from
`docs/api/openapi.yaml` (`pnpm gen:api`); `lib/api/client.ts` wraps `openapi-fetch` and
sends `X-GPUWatch-CSRF: 1` on mutations. `lib/query-keys.ts` holds every query key and the
`staleTime` classes. Next rewrites `/api/*` to the API, so the browser is same-origin and
the session cookie stays first-party. `middleware.ts` sends visitors without a session
cookie to `/login`.

## Important algorithms at a glance

| Algorithm | Where | Document |
| --------- | ----- | -------- |
| Idempotent batch storage with a time window and dropped unknown GPUs | `ingest/service.py::store` | [ingest-and-rollups.md](ingest-and-rollups.md) |
| Dirty ranges and the lag/2 rule | `ingest/service.py::_mark_dirty` | [ingest-and-rollups.md](ingest-and-rollups.md#the-lag2-rule) |
| Watermark rollups, idempotent upserts of whole buckets | `telemetry/rollups.py::tick`, `recompute` | [ingest-and-rollups.md](ingest-and-rollups.md#rollups) |
| Retention that never drops data before it is rolled up | `telemetry/retention.py::run` | [ingest-and-rollups.md](ingest-and-rollups.md#retention) |
| Sample splitting by SM share, then memory, then equally | `costs/attribution.py::attribute` | [cost-attribution.md](cost-attribution.md) |
| Largest-remainder split per GPU-hour | `costs/service.py::split`, `allocations` | [cost-attribution.md](cost-attribution.md#exact-pricing-per-gpu-hour) |
| Idle runs over contiguous minutes | `insights/engine.py::idle_runs` | [insights.md](insights.md) |
| Fire exactly once, resolve exactly once | `alerts/evaluator.py::_fire`, `_resolve` | [alerts.md](alerts.md) |
| Outbox with backoff and signed webhooks | `alerts/notifier.py` | [alerts.md](alerts.md#delivery) |
| Counter deltas and server restarts | `apps/agent/.../inference.py::delta` | [agent.md](agent.md#inference-servers) |
| Histogram quantiles | `inference/histograms.py::quantile` | [agent.md](agent.md#inference-servers) |
| Sliding-window rate limit | `limits/limiter.py` | [HLD.md](HLD.md#caching-layers) |
| Config cache with a cluster-wide version stamp | `core/cache.py` | [HLD.md](HLD.md#caching-layers) |

# Configuration

Everything is configured through environment variables. The API reads them once at boot
through `Settings` in [`core/config.py`](../../apps/api/src/gpuwatch/core/config.py)
(names are case-insensitive) and validates them; with `ENVIRONMENT=production`, unsafe
values stop the process ([boot guards](#production-boot-guards)). The agent reads its
`GPUWATCH_*` variables in
[`config.py`](../../apps/agent/src/gpuwatch_agent/config.py).

- [API: core](#api-core)
- [API: database and cache](#api-database-and-cache)
- [API: sessions and keys](#api-sessions-and-keys)
- [API: secret sealing](#api-secret-sealing)
- [API: AWS and storage](#api-aws-and-storage)
- [API: mail and links](#api-mail-and-links)
- [API: request limits](#api-request-limits)
- [API: ingest](#api-ingest)
- [API: health and retention](#api-health-and-retention)
- [API: worker](#api-worker)
- [API: webhooks](#api-webhooks)
- [API: process and CLI variables](#api-process-and-cli-variables)
- [Insight thresholds (dashboard)](#insight-thresholds-dashboard)
- [Dashboard](#dashboard)
- [Agent](#agent)
- [Local stack ports](#local-stack-ports)
- [Test suite](#test-suite)
- [Production boot guards](#production-boot-guards)

## API: core

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `ENVIRONMENT` | `development` | `development`, `test` or `production`. `production` turns on the boot guards; `seed-demo` refuses it |
| `GPUWATCH_CLOUD` | `local` | `local`, `floci` or `aws`; informational, except that `aws` with `AWS_ENDPOINT_URL` set is refused in production |
| `LOG_LEVEL` | `INFO` | Python log level for the JSON logs |
| `OTEL_ENABLED` | `false` | Install the OpenTelemetry SDK with an OTLP HTTP exporter. Configure it with the standard `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_SERVICE_NAME` variables |

## API: database and cache

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `DATABASE_URL` | `postgresql+asyncpg://gpuwatch:gpuwatch@localhost:4442/gpuwatch` | SQLAlchemy async URL (asyncpg driver) |
| `DB_POOL_SIZE` | `10` | Connections kept open per process |
| `DB_MAX_OVERFLOW` | `20` | Extra connections under load per process |
| `REDIS_URL` | empty | Redis for the live view, rate limits and config invalidation. Empty: all three run in process, which is exact for one API process; use Redis for several replicas or `WEB_CONCURRENCY` above 1 |

## API: sessions and keys

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `SESSION_SECRET` | a development value | HS256 key for dashboard session tokens. Production: random, at least 32 characters |
| `API_KEY_PEPPER` | a development value | HMAC pepper for API keys, host tokens and enrolment tokens. Production: random, at least 32 characters, different from `SESSION_SECRET`. Changing it invalidates every key and token |
| `SESSION_TTL_HOURS` | `12` | Session lifetime |
| `COOKIE_SECURE` | `false` | Mark the session cookie `Secure`. Production requires `true` |
| `CORS_ORIGINS` | `http://localhost:4410` | Comma-separated browser origins allowed to call the API directly. The dashboard proxies `/api`, so normally only its own origin |

## API: secret sealing

Webhook signing secrets are sealed before they reach the database.

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `KEY_MODE` | `local` | `local` (AES-256-GCM with a key derived from `LOCAL_MASTER_KEY`) or `kms` |
| `LOCAL_MASTER_KEY` | a development value | Used with `KEY_MODE=local`. Production: random, at least 32 characters |
| `KMS_KEY_ID` | `alias/gpuwatch-local` | Key id, ARN or alias used with `KEY_MODE=kms` |

## API: AWS and storage

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `AWS_REGION` | `us-east-1` | Region for every AWS client |
| `AWS_ENDPOINT_URL` | unset | Endpoint override (Floci locally). Leave unset on AWS |
| `S3_FORCE_PATH_STYLE` | `false` | Path-style S3 addressing (needed for the emulator) |
| `STORAGE` | `local` | Where cost report CSVs go: `local` or `s3` |
| `LOCAL_STORAGE_DIR` | `./.data/reports` | Directory for `STORAGE=local` |
| `REPORTS_BUCKET` | `gpuwatch-local-reports` | Bucket for `STORAGE=s3` (objects written with SSE-KMS) |

Credentials come from the standard AWS chain (environment, profile, task role); the API
never reads static keys from its own settings.

## API: mail and links

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `MAIL_MODE` | `log` | `log` (written to the log, nothing delivered), `smtp` or `ses` |
| `MAIL_FROM` | `GPUWatch <alerts@gpuwatch.local>` | Sender of alert email (a verified SES identity with `ses`) |
| `SMTP_HOST` | `localhost` | SMTP server for `MAIL_MODE=smtp` |
| `SMTP_PORT` | `1025` | |
| `SMTP_USER`, `SMTP_PASSWORD` | unset | Login, when both are set |
| `SMTP_STARTTLS` | `false` | Upgrade the connection with STARTTLS |
| `DASHBOARD_URL` | `http://localhost:4410` | Public dashboard URL, used for links in notifications |

## API: request limits

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `MAX_BODY_BYTES` | `8000000` | Largest request body, chunked or not (413 above) |
| `DEFAULT_RPM_LIMIT` | `600` | Requests per minute for an API key without its own limit |

Sign-in is limited to 20 attempts per minute per client address, and 5 failures lock an
account for 15 minutes (fixed in code).

## API: ingest

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `INGEST_RPM_PER_HOST` | `240` (min 10) | Batches per minute per host (429 above). At a 5 s interval an agent sends 12 a minute, plus spool replays |
| `INGEST_MAX_SAMPLES` | `20000` (min 100) | Samples plus processes plus inference rows per batch (a larger batch is refused whole) |
| `INGEST_MAX_FUTURE_S` | `120` | Rows further in the future than this are dropped (clock skew) |
| `SIMULATED_BACKFILL_DAYS` | `45` (1 to 400) | How old rows from simulated hosts may be (demo backfill). Real hosts are limited to `RAW_RETENTION_DAYS` |

## API: health and retention

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `HOST_OFFLINE_AFTER_S` | `60` (min 15) | A host that has not reported for this long is disconnected and the "Agent offline" rule fires |
| `LIVE_TTL_S` | `300` | How long a live sample stays "live" (KV key TTL, and the window of the Postgres fallback) |
| `RAW_RETENTION_DAYS` | `7` (1 to 60) | Raw GPU and process samples (daily partitions) and inference samples. Also the reach of re-attribution |
| `ROLLUP_1M_RETENTION_DAYS` | `30` (1 to 400) | Minute rollups |
| `ROLLUP_1H_RETENTION_DAYS` | `400` (30 to 3650) | Hour rollups, hourly workload usage, hourly inference rollups |
| `REPORT_RETENTION_DAYS` | `30` | Cost report CSVs and their rows. Keep it equal to the bucket lifecycle on AWS |

## API: worker

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `WORKER_TICK_S` | `5.0` | Rollup job interval |
| `ALERT_EVAL_INTERVAL_S` | `15` (min 5) | Alert evaluation interval |
| `INSIGHT_EVAL_INTERVAL_S` | `60` (min 15) | Insights engine interval |
| `ROLLUP_LAG_S` | `90` (min 10) | How long after a minute ends before the rollup closes it; rows older than half of this create dirty ranges |
| `WORKER_METRICS_PORT` | `9464` | Port of the worker's own `/metrics`; `0` turns it off |
| `METRICS_TOKEN` | unset | When set, the API's `/metrics` requires `Authorization: Bearer <token>` |

Partitions and retention run hourly and notifications every 2 s (fixed in code).

## API: webhooks

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `WEBHOOK_ALLOW_PRIVATE` | `true` | Allow webhooks to loopback, private and carrier-grade NAT addresses (an internal chat relay). Link-local and cloud metadata addresses are refused regardless. The AWS environments set `false` unless you opt in |
| `WEBHOOK_TIMEOUT_S` | `10.0` | Timeout per webhook request (connect: 5 s) |

## API: process and CLI variables

Read by the `gpuwatch` CLI or the server process, not by `Settings`:

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `PORT` | `4430` | `gpuwatch serve` port (the containers use 8080) |
| `WEB_CONCURRENCY` | `1` | uvicorn worker processes per container. Keep 1 and scale replicas instead; above 1 needs Redis |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Addresses whose `X-Forwarded-For` uvicorn trusts (the load balancer network; the VPC CIDR on AWS) |
| `GPUWATCH_OWNER_PASSWORD` | unset | Password for `gpuwatch create-owner` (otherwise it prompts) |
| `GPUWATCH_DEMO_TOKEN_FILE` | `/demo/enrolment-token` | Where `seed-demo` writes the simulated enrolment token |
| `GW_DEMO_PASSWORD` (or `DEMO_PASSWORD`) | `WatchDemo2026` | Password of the demo users created by `seed-demo`. `make env` generates a random one |
| `GPUWATCH_API_URL`, `DEMO_EMAIL`, `DEMO_PASSWORD` | `http://localhost:4430`, `owner@gpuwatch.local`, empty | Used by `make bench` |

## Insight thresholds (dashboard)

The idle rule and insight thresholds are not environment variables: admins edit them in
Settings, Insight rules (`PUT /api/v1/settings/insights`), and they are stored in the
database. Defaults and ranges are listed in
[insights.md](../architecture/insights.md#thresholds). `idle_util_pct` also sets what
cost attribution counts as idle.

## Dashboard

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `API_INTERNAL_URL` | `http://localhost:4430` | Where the Next.js server proxies `/api/*`, `/healthz`, `/readyz`, `/docs` and `/openapi.json` (server side only; the browser never sees it) |
| `PORT` | `4410` (`pnpm dev`), 8080 in the container | Listen port |

## Agent

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `GPUWATCH_URL` | `http://localhost:4430` | The GPUWatch API (the ALB URL on AWS). Batches go to `<url>/ingest/v1/batches` |
| `GPUWATCH_ENROLMENT_TOKEN` | unset | Enrolment token (`gwe_...`) from Hosts, "Add a host". Used once, and again if the host token is rotated or revoked |
| `GPUWATCH_ENROLMENT_TOKEN_FILE` | unset | A file holding the enrolment token (read when the variable above is empty) |
| `GPUWATCH_COLLECTOR` | `nvml` | `nvml`, `dcgm` or `simulated` |
| `GPUWATCH_INTERVAL_S` | `5` | Seconds between readings (1 to 300) |
| `GPUWATCH_DCGM_URL` | `http://localhost:9400/metrics` | DCGM exporter endpoint for `GPUWATCH_COLLECTOR=dcgm` |
| `GPUWATCH_LABELS` | empty | `key=value,key=value` attached to the host at enrolment (merged with the token's labels) |
| `GPUWATCH_INFERENCE` | empty | Inference servers to scrape: `name=vllm\|tgi,url[,gpu_index+gpu_index]`, several separated by `;` |
| `GPUWATCH_STATE_DIR` | `/var/lib/gpuwatch-agent` | Host token, spool, machine id, backfill marker |
| `GPUWATCH_MACHINE_ID` | `/etc/machine-id` | Stable machine identity (re-enrolling keeps the host). Falls back to `/var/lib/dbus/machine-id`, then a random id in the state dir |
| `GPUWATCH_HOSTNAME` | the system host name | Host name reported to the server |
| `GPUWATCH_SPOOL_MAX_MB` | `200` | Disk spool bound; past it, the oldest batches are dropped |
| `GPUWATCH_TIMEOUT_S` | `15` | HTTP timeout to the API (connect: 5 s) |
| `GPUWATCH_SIM_PROFILE` | `workstation` | Simulated collector profile: `training`, `inference` or `workstation` |
| `GPUWATCH_SIM_BACKFILL_DAYS` | `0` | Days of simulated history to send once (simulated hosts only) |

## Local stack ports

Set in `deploy/compose/.env` (generated by `make env`; see `.env.example`):

| Variable | Default | Service |
| -------- | ------- | ------- |
| `GW_WEB_PORT` | `4410` | Dashboard |
| `GW_API_PORT` | `4430` | API |
| `GW_MAILPIT_PORT` | `4425` | Mailpit UI |
| `GW_SMTP_PORT` | `4426` | Mailpit SMTP (used by the integration suite) |
| `GW_MOCK_VLLM_PORT` | `4450` | Mock vLLM (demo) |
| `GW_PG_PORT` | `4442` | Postgres |
| `GW_REDIS_PORT` | `4479` | Redis |
| `GW_FLOCI_PORT` | `4466` | Floci |
| `GW_LOG_LEVEL` | `INFO` | `LOG_LEVEL` of api and worker |
| `GW_REDIS_URL` | `redis://redis:6379/0` | Set it empty to run the whole stack without Redis |
| `GW_DEMO_DAYS` | `30` | History the simulated demo hosts backfill |

`make tf-aws-on-floci` uses port 4496 (`TF_FLOCI_PORT`).

## Test suite

Read by `apps/api/tests/integration/conftest.py` and `scripts/test-matrix.sh`:

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://gpuwatch:gpuwatch@localhost:4442/gpuwatch_test` | Must contain `test` in the database name; non-local hosts need `ALLOW_REMOTE_TEST_DB=true` |
| `TEST_REDIS_URL` | `redis://localhost:4479/15` | |
| `TEST_CACHE` | `redis` | `memory` runs the suite with no Redis |
| `TEST_SMTP_PORT` | `4426` | Mailpit SMTP |
| `TEST_MAILPIT_API` | `http://localhost:4425/api/v1` | Mailpit API, to read delivered alert email |
| `TEST_KEY_MODE`, `TEST_STORAGE`, `TEST_MAIL_MODE` | `local`, `local`, `smtp` | Backend matrix (`kms`, `s3`, `ses` against Floci) |
| `TEST_AWS_ENDPOINT`, `TEST_KMS_KEY_ID`, `TEST_REPORTS_BUCKET` | unset, `alias/gpuwatch-local`, `gpuwatch-local-reports` | Floci targets for the matrix |

## Production boot guards

With `ENVIRONMENT=production` the API refuses to start when `SESSION_SECRET` or
`API_KEY_PEPPER` is a demo value or shorter than 32 characters, when they are equal, when
`KEY_MODE=local` without a strong `LOCAL_MASTER_KEY`, when `GPUWATCH_CLOUD=aws` with an
`AWS_ENDPOINT_URL`, or when `COOKIE_SECURE` is false. The error lists every problem at
once.

# Testing

GPUWatch has several layers of automated checks, and each proves something different. At
0.1.0 there are 111 API unit, 34 agent, 36 dashboard, 87 integration and 19 browser tests;
the README's Testing table keeps the current counts. This guide describes what each gate covers and how to run it.

| Gate | Command | Needs | Proves |
| ---- | ------- | ----- | ------ |
| Lint | `make lint` | uv, pnpm | ruff check and ruff format for the API and the agent, ESLint for the dashboard |
| Typecheck | `make typecheck` | uv, pnpm | mypy `--strict` for the API and the agent, `tsc --noEmit` for the dashboard |
| Unit | `make test` | uv, pnpm | Pure logic with no database, no network and no GPU: API (pytest), agent (pytest, with a faithful NVML fake) and dashboard (Vitest) |
| Integration | `make test-integration` | Docker | The real API in-process against real Postgres, Redis and Mailpit, including every acceptance criterion |
| Option matrix | `make test-matrix` | `make up` (Floci) | The integration suite under every cache, key, storage and mail backend (8 runs) |
| Browser e2e | `make e2e` | `make up && make demo` | User journeys through the real dashboard, API and simulated agents (Playwright, Chromium) |
| Browser QA | `make qa` | `make up && make demo` | Every page in light and dark, desktop and phone width, with no console errors, failed requests, broken images, error states or horizontal overflow (Puppeteer) |
| Sanitization | `make sanitize` | bash, git | No credentials, cloud identifiers, committed env files or em/en dashes in the tree |
| Terraform validate | `make tf-validate` | Docker or terraform | `terraform validate` for `local-floci`, `aws-dev` and `aws-prod` |
| Terraform lint | `make tf-lint` | Docker | tflint over every module and environment |
| Terraform security | `make tf-security` | Docker | checkov policy scan (inline, reasoned skips only) |
| AWS on Floci | `make tf-aws-on-floci` | Docker | The full `aws-dev` environment planned, applied, re-planned and destroyed against a throwaway Floci |
| Service benchmark | `make bench` | `make up && make demo` | Ingest and dashboard latency and throughput of the running stack (numbers go in the README) |

## Static checks

```bash
make lint typecheck
```

- `apps/api`: `uv run ruff check src tests`, `uv run ruff format --check src tests`,
  `uv run mypy src` (strict).
- `apps/agent`: the same three commands in its own uv project.
- `apps/web`: `pnpm lint` (ESLint) and `pnpm typecheck` (`tsc --noEmit`).

## Unit tests

```bash
make test
```

Runs `uv run pytest tests/unit -q` in `apps/api`, `uv run pytest -q` in `apps/agent` and
`pnpm test` (Vitest) in `apps/web`.

| Location | Covers |
| -------- | ------ |
| `apps/api/tests/unit/core/` | Settings and the production boot guards, Redis being optional, privacy defaults, the KV store and the config cache (single flight, cross-instance invalidation, TTL, the invalidation race), money conversion and rounding, schemas, JSON logs with redaction, the error envelope, sealing (context binding, fresh nonces) and storage (path traversal), passwords, sessions and token kinds |
| `apps/api/tests/unit/costs/test_attribution.py` | The largest-remainder split, SM share then memory then equal weighting, idle and unattributed buckets, held idle time, seconds adding up per GPU-hour, workload rule matching, rate precedence |
| `apps/api/tests/unit/insights/test_engine.py` | Every insight rule with exact inputs: idle runs, idle cost and monthly estimates, unknown utilization, underused, oversized with a cheaper card from your rates, throttling, memory pressure, hardware errors, the 24 hour health window, inference rules, money formatting |
| `apps/api/tests/unit/alerts/test_alerts_unit.py` | SSRF address classes and URL checks, the webhook signature, backoff, email text, rule descriptions |
| `apps/api/tests/unit/inference/test_histograms.py` | Histogram merge and quantile interpolation (open bucket, no observations) |
| `apps/api/tests/unit/test_privacy.py` | Acceptance criterion 12: no hardcoded outbound hosts in the API or the agent, no telemetry or tracing on by default |
| `apps/api/tests/unit/system/test_openapi_drift.py` | `docs/api/openapi.yaml` matches the app and every operation is documented. `make openapi` regenerates it |
| `apps/agent/tests/test_collectors.py` | The NVML collector against [`fakenvml.py`](../../apps/agent/tests/fakenvml.py) (every supported field, unsupported fields as null, no process utilization, no process listing, a lost GPU, init failure, XID events), DCGM exporter parsing, the simulator's determinism and scenarios, `/proc` enrichment |
| `apps/agent/tests/test_inference.py` | vLLM and TGI snapshots, per-interval deltas, server restarts, TGI without TTFT or KV cache, unreachable servers, the mock server through the real scraper |
| `apps/agent/tests/test_agent.py` | Enrolment, the batch contract, spooling and in-order replay, refused batches, re-enrolment on a rotated token, a degraded collector, the capped interval, one-time backfill, the bounded spool, configuration parsing, acceptance criterion 11 for the agent (no process control calls, no listening socket) |
| `apps/web/test/` | Formatting, error messages, auth redirects and keys, domain helpers and components |

## Integration tests

```bash
make test-integration
```

`scripts/test-db.sh` reuses the Compose Postgres, Redis and Mailpit when they are up, and
otherwise starts just those three. The suite runs `apps/api/tests/integration` with
coverage against `gpuwatch_test` (created fresh for the session and migrated with
Alembic), Redis database 15 and Mailpit's SMTP and API. A local webhook receiver runs in a
background thread.

Safety: the suite truncates every table, so it refuses a database whose name lacks `test`,
and any host other than `localhost`, `127.0.0.1` or `postgres` unless
`ALLOW_REMOTE_TEST_DB=true`. Override the targets with `TEST_DATABASE_URL`,
`TEST_REDIS_URL`, `TEST_SMTP_PORT` and `TEST_MAILPIT_API`
([configuration.md](configuration.md#test-suite)).

| File | Proves |
| ---- | ------ |
| `test_acceptance.py` | The acceptance criteria of [PLAN.md](../PLAN.md), one or more tests each: (1) a sample reaches the live snapshot and an open SSE stream within 5 s; (2) an unreported metric stays null in the API; (3) a silent agent is disconnected and alerts once, resolved when it returns; (4) idle with a model loaded costs rate times idle hours; (5) workload costs plus idle equal the GPU cost exactly; (6) a hot GPU alerts once by email (Mailpit) and signed webhook and resolves once; (7) spool and replay without duplicates, resending is a no-op; (8) power capping during busy time is named; (9) inference TTFT p95, tokens per second and cost per million tokens match a hand calculation, a server without TTFT reports null; (10) a driver failure shows the reason and the GPU as lost; (11) agents reach only ingest and get no commands; (12) a viewer reads but cannot change (privacy defaults are unit tested) |
| `test_fleet.py` | Enrolment tokens (shown once, limits, expiry), re-enrolment rotating the token, batches updating hosts and inventory, the time window and simulated backfill, GPUs following their UUID, rename, relabel and revoke, retire and restore, 404s, malformed host tokens |
| `test_telemetry.py` | Late samples rolled up exactly once, resolution by range, processes and workload shares, unattributed busy time, retention and partitions, insight settings, insight lifecycle, overview and explanation, one rollup across replicas, the worker schedule, a failing job not stopping the others |
| `test_costs.py` | Rate precedence, validation and conflicts, unpriced hours, workload rules applied retroactively, hourly and daily series, range validation, CSV reports |
| `test_alerts.py` | Built-in rules, rule validation, scope labels, unreported metrics never firing, short breaches, disabling rules, SSRF refusals, channel CRUD and secret handling, failed deliveries backing off then failing, disabled channels, retired GPUs resolving their lost alert |
| `test_admin.py` | Sign-in and lockout, CSRF, the role matrix, read-only API keys, per-key rate limits, owner guards, password changes ending other sessions, the append-only audit log, system info, health and metrics, the metrics token |
| `test_hardening.py` | Lone surrogates as 422, chunked bodies over the limit, oversized batches refused whole, hostile metric values, cross-host GPU writes, the per-host ingest limit, forged `X-Forwarded-For`, parallel wrong passwords, server-side sign-out, signed-out sessions surviving cache eviction, uncached login responses, racing owner demotions and user creates, concurrent batches, concurrent alert evaluations firing once, security headers |
| `test_backends.py` | The configured cache, key, storage and mail backends are the ones in use, with round trips through storage and sealing |

## Option matrix

```bash
make up
make test-matrix
```

`scripts/test-matrix.sh` checks that Floci answers on `localhost:4466`, then runs the
integration suite eight times:

| Axis | Values | Set by |
| ---- | ------ | ------ |
| Cache | `redis`, `memory` (no Redis at all) | `TEST_CACHE` |
| Keys | `local` (AES-GCM), `kms` (Floci KMS, `alias/gpuwatch-local`) | `TEST_KEY_MODE` |
| Storage | `local` (disk), `s3` (Floci S3, `gpuwatch-local-reports`) | `TEST_STORAGE` |
| Mail | `smtp` (Mailpit), `ses` (Floci SES, `gpuwatch.local` identity); SES rides with the KMS runs to keep it at 8 | `TEST_MAIL_MODE` |

The KMS key, the bucket and the SES identity are the ones the `local-floci` Terraform
created during `make up`. It prints `matrix: all 8 combinations passed` or lists the
failing ones.

## Browser end-to-end tests

```bash
make up && make demo
make e2e
```

Playwright (Chromium) against `http://localhost:4410`, signing in with the demo password
from `deploy/compose/.env`. Suites in `e2e/tests/`:

| Suite | Journeys |
| ----- | -------- |
| `01-auth` | Wrong passwords explained, protected pages redirect to sign in, a crafted `next=` cannot leave the site, signing out ends the session for good |
| `02-live-and-gpu` | The live view shows every demo GPU; a GPU page explains its cost |
| `03-hosts` | Adding a host: a token and the install command |
| `04-keys-and-api` | A read-only API key reads the REST API |
| `05-insights-and-costs` | Insights rank waste with evidence; costs break spend down and export a CSV; a rate is added |
| `06-alerts` | An email channel receives a test notification |
| `07-people-and-account` | An owner adds a user; password change; viewers have no Users or Audit pages; the theme sticks |
| `08-configuration` | API keys edited in place; insight rules edited from Settings; inference metrics and cost per million tokens |

`E2E_HEADED=1` watches the run; the report lands in `e2e/playwright-report`.

## Browser QA

```bash
make qa
```

`scripts/qa/qa.mjs` signs in through the real form and visits every page (login, overview,
live, a GPU, hosts, inference, insights, every Costs and Alerts tab, keys, users, audit,
settings) in
light and dark mode at desktop and phone width. It fails on console errors, failed or
4xx/5xx requests, broken images, error states and horizontal overflow, and saves a
screenshot of each. `QA_PAGES`, `QA_THEMES` and `QA_SIZES` narrow a run.

## Infrastructure

```bash
make tf-validate tf-lint tf-security
make tf-aws-on-floci
```

- `tf-validate` runs `terraform init -backend=false` and `validate` for each environment,
  with a local terraform or the pinned `hashicorp/terraform:1.16.6` image.
- `tf-lint` runs tflint v0.64.0 recursively (plugins cached in a Docker volume).
- `tf-security` runs checkov 3.3.30 over `infra/terraform`.
- `tf-aws-on-floci` copies the Terraform tree to a temporary directory, starts a
  throwaway Floci on port 4496, then plans, applies, re-plans (no additions or
  replacements allowed) and destroys the full `aws-dev` environment. It catches plan and
  apply time errors that `validate` cannot see. The repository is not modified.

`make up` also applies `local-floci` on every start.

## Sanitization

```bash
make sanitize
```

`scripts/check-sanitization.sh` scans the files git would commit for AWS access keys,
private keys, 12-digit numbers that could be account ids, AWS resource ids, RDS and
ElastiCache endpoints, common token formats, em and en dashes, and committed env files.
It prints `sanitization: clean` or the offending lines. Run it before every commit.

## In CI

`.github/workflows/checks.yml` runs lint, typecheck and unit tests for the API, the agent
and the dashboard on every push and pull request. The full pipeline (integration tests
with Postgres, Redis and Mailpit service containers, image builds, Terraform, security
scans, e2e) is in `.github/workflows-full/` and opt-in; see its
[README](../../.github/workflows-full/README.md).

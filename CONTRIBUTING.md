# Contributing

Thanks for helping improve Euron Open GPUWatch. This guide covers the layout, the
workflow, the bar a change has to clear, and the conventions the codebase follows.

## Ground rules

- **Open an issue first** for anything larger than a bug fix or a docs tweak, so we can
  agree on the approach before you invest time.
- **One concern per pull request.** A refactor and a feature are two PRs.
- **Security issues go through private reporting**, never a public issue. See
  [SECURITY.md](SECURITY.md).
- By contributing you agree your work is released under the [MIT License](LICENSE).

## Project layout

```
apps/api/         FastAPI API, worker and CLI (package gpuwatch): src/gpuwatch/<domain>/, tests/unit, tests/integration
apps/agent/       the agent that runs on GPU machines (package gpuwatch_agent): collectors, inference scraping,
                  spool, simulator, mock vLLM; tests/ with a faithful NVML fake
apps/web/         Next.js 15 dashboard: src/app (routes), src/features/<domain>, src/components, src/lib
e2e/              Playwright suites against make up && make demo
infra/docker/     api, web and agent Dockerfiles (multi-stage, non-root, pinned bases)
infra/terraform/  modules/ and envs/{local-floci,aws-dev,aws-prod}
deploy/compose/   compose.yaml plus the floci and aws overlays, .env.example
scripts/          sanitization, env generation, test database, test matrix, tf-aws-on-floci, AWS deploy, qa/
docs/             architecture (HLD, LLD, data model, security, subsystems, ADRs), guides, api/openapi.yaml
examples/         small scripts against the REST API and the webhook contract
```

[docs/architecture/LLD.md](docs/architecture/LLD.md) describes every package.

## Development setup

Requirements: Docker, Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 and
pnpm 9 (`corepack enable`).

```bash
make up          # Postgres, Redis, Mailpit, Floci (provisioned by Terraform), api, worker, web
make demo        # demo users, rates and rules, three simulated GPU hosts, a mock vLLM, 30 days of history
make test        # unit tests: API, agent and web
```

Working on one part outside containers:

```bash
cd apps/api   && uv sync && uv run gpuwatch --help           # serve, worker, migrate, seed-demo, ...
cd apps/agent && uv sync && uv run gpuwatch-agent check       # GPUWATCH_COLLECTOR=simulated without a GPU
cd apps/web   && pnpm install && pnpm dev                     # http://localhost:4410, proxies /api to :4430
```

[docs/guides/quickstart-local.md](docs/guides/quickstart-local.md) walks through the local
stack in detail.

## Before you open a pull request

Each of these must pass ([docs/guides/testing.md](docs/guides/testing.md) explains what
each covers):

```bash
make lint typecheck test
make test-integration                  # the API against real Postgres, Redis and Mailpit
make test-matrix                       # when you touched a backend (cache, keys, storage); needs make up
make e2e                               # when you touched a dashboard flow or infrastructure
make qa                                # when you touched the UI: every page, light and dark, desktop and phone
make tf-validate tf-lint tf-security   # when you touched infra/terraform
make tf-aws-on-floci                   # same: apply and destroy aws-dev against Floci
make openapi                           # when you changed an endpoint (a test checks drift); then pnpm gen:api in apps/web
make sanitize                          # no credentials, account ids, resource ids or dashes
```

## Conventions

**Package by domain.** `apps/api/src/gpuwatch/<domain>/` owns its `router.py` (HTTP
only), `schemas.py` (the public contract), `service.py` (rules) and `models.py`.
Dependencies point inward: router, service, data. A domain calls another domain's service,
never its router.

**Not reported is null.** Every metric is optional from the agent to the database to the
dashboard. Never turn a missing value into 0, in an aggregate, a chart or a finding. A new
metric column is nullable, its rollup averages only reported values, and the UI shows "Not
available".

**Money is integer nano-dollars.** Columns and fields named `*_nusd`, Python `int`. A new
cost figure is a grouping of the existing exact allocations
([cost-attribution.md](docs/architecture/cost-attribution.md)), never a fresh
multiplication that rounds on its own.

**Observe only.** The agent opens no port and runs nothing it receives; no API route
starts, stops or signals a process. Tests check both. A change that would weaken this
needs an ADR first.

**The insights engine stays pure.** `insights/engine.py` has no I/O and no clock: it takes
plain data and returns findings, so every rule is unit tested with exact inputs. Every
finding carries its evidence; costs are estimates from the user's own rates, never claimed
savings.

**Background work is coordinated in Postgres.** A worker job takes an advisory lock or
claims rows with `FOR UPDATE SKIP LOCKED`; recomputes are idempotent. Never rely on
in-process locks alone.

**Redis is optional.** Every Redis use goes through `core/kv.py`, has an in-process
fallback, and treats a Redis error as a miss or a pass. Security state never lives only in
the KV store. The test matrix runs the whole integration suite without Redis.

**External systems sit behind a Protocol.** Collectors (`Collector` in the agent), key
sealing (`KeySealer`), storage (`ObjectStorage`), mail (`MailSender`), the KV store
(`KV`). Adding a backend means adding an implementation, chosen by configuration, not
editing call sites. No emulator-specific branches.

**Caching is documented.** A new cache or a change to one updates the caching table in
[HLD.md](docs/architecture/HLD.md#caching-layers), with its key, TTL, invalidation trigger
and the test that proves invalidation.

**Configuration is validated.** A new API setting goes in `core/config.py`, is documented
in [docs/guides/configuration.md](docs/guides/configuration.md) in the same PR, and
security-relevant ones are enforced by `Settings.guard()` at boot. Agent settings go in
`apps/agent/src/gpuwatch_agent/config.py` and the same guide.

**Database changes are new migrations.** Change the models, then run
`make migration MSG="what changed"`: it migrates the local Postgres and autogenerates a
revision under `apps/api/src/gpuwatch/migrations/versions/` for you to review. Indexes and
constraints are declared on the models (`__table_args__`), so autogenerate sees them.
Never edit an applied revision. Indexes for every new filter the API exposes belong in the
same revision.

**Frontend.** Routes in `src/app` stay thin; each screen lives in `src/features/<domain>`
with its TanStack Query hooks in `api.ts`. Query keys come from `lib/query-keys.ts`, and
each query picks a deliberate `staleTime` class. API types are generated from the OpenAPI
document, never written by hand. Every async view has loading, error and empty states, and
every empty state says what to do next.

**Comments explain why.** The code says what it does. Comments are for the constraint, the
incident, or the trade-off that made it this way.

**Style.** ruff and mypy `--strict` for Python (API and agent); ESLint and TypeScript
strict for the web. No em dashes or en dashes anywhere, including UI copy and commit
messages (the sanitization check enforces it).

## Commit messages

Imperative mood with an optional scope: `ingest: drop rows for undeclared GPUs`,
`agent: send counter deltas after a server restart`. Explain the why in the body when it is
not obvious. No dashes in messages.

## Architecture decisions

Significant decisions are recorded in [docs/architecture/adr/](docs/architecture/adr/).
If your change reverses or extends one, add a new ADR rather than editing the old one.

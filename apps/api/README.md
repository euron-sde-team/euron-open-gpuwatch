# gpuwatch (API, worker and CLI)

The Python package behind Euron Open GPUWatch: the agent ingest API (`/ingest/v1`), the
dashboard and REST API (`/api/v1`), Prometheus `/metrics`, the background worker (rollups,
cost attribution, insights, alert evaluation, notifications, retention), the CLI, the demo
seed and the benchmark.

```bash
uv sync
uv run gpuwatch --help              # serve, worker, migrate, revision, openapi, create-owner, seed-demo
uv run pytest tests/unit            # no database, no network
make -C ../.. test-integration      # real Postgres, Redis and Mailpit (started if needed)
```

| Command | What it does |
| ------- | ------------ |
| `gpuwatch serve` | The API on `PORT` (4430 by default) |
| `gpuwatch worker` | Every background job; serves its own metrics on `WORKER_METRICS_PORT` |
| `gpuwatch migrate` | Apply the Alembic migrations |
| `gpuwatch revision -m "..."` | Autogenerate a migration against a migrated database (`make migration`) |
| `gpuwatch openapi` | Print the OpenAPI document (`make openapi` writes `docs/api/openapi.yaml`) |
| `gpuwatch create-owner --email ...` | Create or reset an owner (`GPUWATCH_OWNER_PASSWORD` or a prompt) |
| `gpuwatch seed-demo` | Demo configuration and a simulated enrolment token (refuses production) |
| `python -m gpuwatch.bench` | Ingest and dashboard latency against a running stack (`make bench`) |

Layout, conventions and the data flow: [CONTRIBUTING.md](../../CONTRIBUTING.md), the
[low-level design](../../docs/architecture/LLD.md) and the
[configuration reference](../../docs/guides/configuration.md). The agent lives in
[`apps/agent`](../agent).

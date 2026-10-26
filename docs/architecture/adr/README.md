# Architecture Decision Records

Each ADR captures one significant decision: the context that forced it, what we chose,
and what it costs us. ADRs are immutable once accepted. To revisit one, write a new ADR
that supersedes it.

| ADR | Decision | Status |
| --- | -------- | ------ |
| [0001](0001-postgres-for-metrics.md) | Postgres for metrics (partitioned raw samples and rollups), with a Prometheus `/metrics` exposition, instead of a Prometheus server | Accepted |
| [0002](0002-integer-nano-dollars.md) | Money as integer nano-dollars | Accepted |
| [0003](0003-observe-only-agent.md) | An observe-only agent that pushes idempotent batches outbound | Accepted |
| [0004](0004-exact-cost-attribution.md) | Exact cost attribution with a largest-remainder split per GPU-hour | Accepted |
| [0005](0005-rollups-watermark-and-dirty-ranges.md) | Rollups with a watermark and dirty ranges | Accepted |
| [0006](0006-redis-optional-in-process-fallback.md) | Redis is optional, with an in-process fallback | Accepted |
| [0007](0007-python-fastapi-and-nextjs.md) | Python and FastAPI for the API, worker and agent, Next.js for the dashboard | Accepted |
| [0008](0008-local-aws-emulation.md) | Local AWS emulator (Floci), provisioned by the same Terraform as production | Accepted |

**Template:** Status / Date, then Context, Decision, Consequences (good and bad), and
Alternatives considered.

## What and why

<!-- One paragraph: the problem, and how this change solves it. Link the issue. -->

## How it was verified

- [ ] `make lint typecheck test` (API, agent and web)
- [ ] `make test-integration` (if the API, worker, cache or database code changed)
- [ ] `make test-matrix` (if a backend changed: cache, keys or storage)
- [ ] `make e2e` and `make qa` (if a dashboard flow, the UI or infrastructure changed)
- [ ] `make tf-validate tf-lint tf-security tf-aws-on-floci` (if Terraform changed)
- [ ] `gpuwatch-agent check` output attached (if a collector changed and you have a GPU)

## Checklist

- [ ] Docs updated (README, `docs/`, configuration reference) for any behavior or config change
- [ ] New Alembic revision instead of editing an applied one
- [ ] Metrics a driver does not report are still `null`, never 0
- [ ] Cost totals still agree across groupings (money stays integer nano-dollars)
- [ ] The agent still opens no port and runs nothing it receives
- [ ] Caching table in `docs/architecture/HLD.md` updated if a cache was added or changed
- [ ] `make openapi` run if the API changed
- [ ] No secrets, account ids, real hostnames or em/en dashes (`make sanitize` is clean)
- [ ] Security-relevant change? Described the threat and mitigation above

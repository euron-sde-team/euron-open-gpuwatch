# Full CI pipeline (opt-in)

These workflows are the complete quality pipeline for Euron Open GPUWatch. They are kept
here, outside `.github/workflows/`, so they do **not** run on this repository. Only the
fast [`checks`](../workflows/checks.yml) workflow (lint, typecheck and unit tests for the
API, the agent and the dashboard, plus the web build) runs here.

| Workflow | What it runs |
| --- | --- |
| [`ci.yml`](ci.yml) | Sanitization scan and OpenAPI drift; API unit and integration tests on Postgres 16, Redis 7 and Mailpit service containers with an 85% coverage floor; the integration suite again with no Redis at all (`TEST_CACHE=memory`); agent tests with coverage |
| [`security.yml`](security.yml) | gitleaks over full history, CodeQL (Python and TypeScript), pip-audit for the API and the agent, pnpm audit for the dashboard |
| [`terraform.yml`](terraform.yml) | `terraform fmt` and `validate` for every environment, tflint, checkov, and the full `aws-dev` environment applied and destroyed against Floci |
| [`docker.yml`](docker.yml) | Multi-arch (amd64, arm64) builds of the api, web and agent images from `infra/docker/*.Dockerfile`, with the same build contexts as `deploy/compose/compose.yaml` |
| [`e2e.yml`](e2e.yml) | The full stack on the local AWS emulator (`make up`), the demo fleet (`make demo`: three simulated GPU hosts through the real ingest API), the integration suite under every cache, key and storage backend (`make test-matrix`), the Playwright browser tests and the Puppeteer QA sweep |

The integration jobs point the suite at the service containers through the variables read
by `apps/api/tests/integration/conftest.py`: `TEST_DATABASE_URL`, `TEST_REDIS_URL`,
`TEST_SMTP_PORT` (Mailpit SMTP, 1025) and `TEST_MAILPIT_API` (Mailpit's API on 8025, used
to read delivered alert email).

To enable them in your fork, move them into `.github/workflows/`:

```bash
git mv .github/workflows-full/*.yml .github/workflows/
```

Every gate is also runnable locally:
`make lint typecheck test test-integration test-matrix e2e qa tf-validate tf-lint tf-security tf-aws-on-floci sanitize`.

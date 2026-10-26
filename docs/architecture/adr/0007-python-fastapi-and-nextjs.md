# ADR-0007: Python and FastAPI for the API, worker and agent, Next.js for the dashboard

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

GPU tooling is Python first: the official NVML bindings (`nvidia-ml-py`), the Prometheus
client, and the inference servers GPUWatch reads (vLLM, TGI) all live in that ecosystem,
and the ML engineers who install the agent already run Python. The Euron open-source
projects also share a fixed rule: Python and FastAPI backends, Next.js frontends, no
exceptions.

## Decision

- The API, the worker and the CLI are one Python 3.12 package, `gpuwatch`, on FastAPI,
  Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic, redis-py, httpx and boto3, managed
  by uv and checked with ruff and mypy `--strict`. Blocking SDK calls (boto3, SMTP, Argon2)
  run in worker threads.
- The agent is a separate, small Python package, `gpuwatch-agent` (`apps/agent`), with
  three runtime dependencies (`httpx`, `nvidia-ml-py`, `prometheus-client`) and support for
  Python 3.10 to 3.13, so it installs on the GPU machines people already have. It ships as
  a container image or a pip install.
- The dashboard is Next.js 15 (App Router, React 19, TypeScript strict, Tailwind v4,
  shadcn components, TanStack Query v5), proxying `/api` to the API so the browser stays
  same-origin. Its API types are generated from the OpenAPI document.

## Consequences

**Good**
- The NVML collector uses NVIDIA's own bindings; no second implementation of the driver
  API.
- Typed contracts end to end: Pydantic schemas generate the OpenAPI document, a drift test
  keeps `docs/api/openapi.yaml` in sync, and the dashboard's types come from it.
- The agent and the API share a language, which keeps the wire contract easy to test from
  both sides.

**Bad / caveats**
- Python's per-request CPU cost is higher than Go or Rust. Ingest is one transaction per
  batch with `executemany`; the API scales horizontally (stateless processes).
- A Python agent needs an interpreter on the machine (or Docker). The image bundles one.

## Alternatives considered

- **A Go agent.** A single static binary is attractive, but NVML bindings and the test
  fake would be a second implementation, and the program rules fix the stack.
- **A plain React SPA.** Next.js gives routing, code splitting and a same-origin proxy, and
  matches the sibling projects.

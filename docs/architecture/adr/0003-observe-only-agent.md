# ADR-0003: An observe-only agent that pushes idempotent batches outbound

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

GPUWatch needs data from machines that often sit behind NAT or firewalls (workstations,
on-premise nodes, cloud VMs in private subnets). A monitoring tool that can act on those
machines is a remote execution risk; the product promise is that GPUWatch observes and
recommends and never kills or starts a process. Networks fail, and the API restarts, so
data must survive gaps without being counted twice.

## Decision

- **Push, outbound only.** The agent sends `POST /ingest/v1/batches` over HTTPS every
  `GPUWATCH_INTERVAL_S` (5 s). It opens no port; nothing connects to it. Its only other
  calls are local reads (NVML, `/proc`, the DCGM exporter and inference `/metrics` URLs
  configured on the machine).
- **No command channel.** The reply carries counts and `next_in_s`, nothing the agent
  executes. No API route starts, stops or signals a process. Both are tested: over the
  route table (`test_11_agents_can_only_reach_ingest_and_get_no_commands`) and over the
  agent's source (`test_observe_only_the_agent_never_runs_or_kills_anything`).
- **Enrolment.** An admin creates an enrolment token (`gwe_`); the agent exchanges it once
  for a host token (`gwh_`), stored with mode 0600. Re-enrolling the same machine id keeps
  the host and rotates the token. Tokens are stored server side as peppered HMACs.
- **Idempotent batches.** Each batch has a UUID `batch_id`; the server records
  `(host_id, batch_id)` and answers a replay with `duplicate: true` without writing. Row
  primary keys (`(gpu_id, ts)`, ...) ignore duplicates as a second layer.
- **Disk spool.** Batches the server cannot take (network errors, 429, 5xx) are written to
  a bounded spool and replayed oldest first after the next successful send.

## Consequences

**Good**
- Works through NAT and egress-only firewalls; one outbound rule to 443 is enough.
- A compromised GPUWatch server cannot run anything on the machines.
- No lost data during API outages up to the spool size; no duplicates after replay
  (acceptance criterion 7).
- Server-side ingest is stateless per request and scales with API replicas.

**Bad / caveats**
- The server cannot ask for an immediate reading; freshness is bounded by the interval.
- A host token can write false telemetry about its own GPUs (mitigated by scoping, time
  windows, rate limits and revocation; see [threat-model.md](../threat-model.md)).
- Clock skew on the machine matters: rows more than 120 s in the future are dropped.
- Remediation (stopping an idle model) stays a human action until an explicit, opt-in
  design exists (roadmap).

## Alternatives considered

- **Pull (Prometheus style scraping of each machine).** Needs an inbound port and network
  reachability from the server to every machine.
- **A bidirectional channel (WebSocket, gRPC stream) with commands.** Enables remediation,
  but turns the agent into a remote execution surface.
- **At-least-once without ids.** Simpler, but replays after an outage would double count
  cost.

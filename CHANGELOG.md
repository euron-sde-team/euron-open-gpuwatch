# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-26

First public release: the agent, the API and worker, and the dashboard.

### Added

- `gpuwatch-agent`: NVML collector (`nvidia-ml-py`) with per-call fallbacks for metrics a
  card does not support, a DCGM exporter collector, and a deterministic simulated collector
  with training, inference and workstation scenarios; process names, users, container ids,
  memory and SM share; vLLM and TGI `/metrics` scraping with counter-reset handling; a disk
  spool with replay, idempotent batch ids and re-enrolment on a revoked or lost token. It
  opens no port and never starts or stops a process.
- Enrolment: one-time `gwe_` tokens with expiry, machine limits and labels, exchanged for a
  per-host `gwh_` token; hosts can be renamed, relabelled and revoked.
- Ingest: validated batches with per-host rate limits, deduplicated by batch id, written to
  `gpu_samples` and `process_samples` range-partitioned by day.
- Live view: the newest sample per GPU in Redis (or in process), served as a snapshot and
  as a server-sent event stream, with polling as the fallback.
- Rollups: 1 minute and 1 hour, idempotent, with a watermark and a dirty-range queue for
  late data; retention drops whole partitions (7 days raw, 30 days of minutes, 400 days of
  hours by default).
- Cost: hourly rates per GPU, host or model; every interval attributed to processes by SM
  share, then memory, then equally; idle split into nothing running and held idle; workload
  rules by process, user, container or label, re-applicable to history; totals in integer
  nano-dollars with largest-remainder splits; summaries, series and CSV reports in S3 or on
  disk.
- Insights: idle with a model loaded, idle and empty, underused, oversized memory,
  throttled, memory pressure, hardware errors, inference queueing and inference
  overprovisioned, each with evidence, an estimated monthly cost and what to do;
  acknowledge, dismiss, automatic resolution; thresholds editable in the dashboard.
- Alerts: rules on GPU and host metrics with durations, scopes and severities, built-in
  rules for offline agents, lost GPUs, heat and full memory; one firing per rule and target;
  email (log, SMTP or SES) and HMAC-signed webhooks through a transactional outbox with
  backoff.
- Inference: per-endpoint throughput, TTFT, inter-token and end-to-end latency
  percentiles from histograms, queue depth, KV cache use, GPU utilization, cost per million
  tokens and per request.
- Dashboard: overview, live, hosts, GPU detail with a cost explanation, insights, costs,
  alerts, inference, API keys, users, audit log and settings; light and dark; down to phone
  width.
- Platform: owner, admin and viewer roles, read-only `gwk_` API keys with rate limits, CSRF,
  an append-only audit log, Prometheus `/metrics` for the fleet and the service, JSON logs
  with request ids, `/healthz` and `/readyz`.
- Local stack on Docker Compose with Floci (S3, KMS, SES, Secrets Manager) provisioned by
  Terraform, Mailpit, a mock vLLM server and three simulated demo agents; `make demo`.
- Terraform modules for network, database, cache, storage, KMS, secrets, email, ECR, service
  and observability, with `local-floci`, `aws-dev` and `aws-prod` environments.

### Security

- Tokens and keys stored only as peppered HMACs; webhook secrets sealed with KMS (or a local
  AES-GCM key) bound to their channel.
- Webhook destinations resolved and checked before every delivery; metadata and link-local
  addresses always refused.
- argon2id passwords, atomic lockout and per-IP throttling, sessions ended on sign-out,
  password change or role change; production boot guards refuse unsafe configuration.

[Unreleased]: https://github.com/euron-sde-team/euron-open-gpuwatch/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/euron-sde-team/euron-open-gpuwatch/releases/tag/v0.1.0

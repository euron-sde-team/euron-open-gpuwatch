# Operations

Day-two tasks for a running GPUWatch: data lifecycle, backups, scaling, monitoring,
secrets, access, and re-attributing costs. Settings are in
[configuration.md](configuration.md); the AWS deployment in [deploy-aws.md](deploy-aws.md).

- [Processes](#processes)
- [Retention and partitions](#retention-and-partitions)
- [Backups and restore](#backups-and-restore)
- [Scaling](#scaling)
- [Health checks](#health-checks)
- [Prometheus](#prometheus)
- [Alarms](#alarms)
- [Logs](#logs)
- [Rotating secrets](#rotating-secrets)
- [Revoking hosts, tokens and keys](#revoking-hosts-tokens-and-keys)
- [Re-attributing costs with workload rules](#re-attributing-costs-with-workload-rules)
- [Users and owners](#users-and-owners)

## Processes

| Process | Command | Notes |
| ------- | ------- | ----- |
| API | `gpuwatch serve` | Stateless; scale horizontally. 30 s graceful shutdown |
| Worker | `gpuwatch worker` | Runs every background job; safe to run more than one |
| Migrations | `gpuwatch migrate` | One-off before a new version starts (`migrate` service locally, `make aws-migrate` on AWS) |
| Dashboard | `node server.js` (Next.js standalone) | Stateless; proxies `/api` to the API |

## Retention and partitions

The worker keeps the data lifecycle on its own:

- **Partitions** of `gpu_samples` and `process_samples` are created every hour from
  yesterday to three days ahead (and by ingest on demand for older days).
- **Retention** runs every hour: raw partitions are dropped once their day is past
  `RAW_RETENTION_DAYS` **and** the rollup watermark (never before they are rolled up);
  rollups and usage are trimmed by `ROLLUP_1M_RETENTION_DAYS` and
  `ROLLUP_1H_RETENTION_DAYS`; old batch ids, notifications and reports go too. The full
  table is in [data-model.md](../architecture/data-model.md#retention-summary).

Sizing: at the default 5 s interval each GPU writes 17,280 raw samples a day (plus one row
per process per sample). Keeping more raw days costs disk roughly linearly; longer ranges
are served by rollups regardless. Raising `RAW_RETENTION_DAYS` also widens how far back
re-attribution reaches; lowering it frees disk at the next hourly run.

To see partitions:

```sql
SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
JOIN pg_class p ON p.oid = i.inhparent WHERE p.relname = 'gpu_samples' ORDER BY 1;
```

If the worker was stopped for days, it catches up: partitions are created on demand,
the watermark rolls forward in 6-hour steps, and agents' spooled batches create dirty
ranges that are recomputed.

## Backups and restore

Postgres holds everything that matters: configuration, inventory, history, findings,
alerts, users and the audit log. Redis holds only rebuildable state and needs no backup.
Report CSVs are re-creatable from the data.

- **AWS:** RDS automated backups (3 days in `aws-dev`, 14 in `aws-prod`, plus a final
  snapshot on destroy in prod). Restore to a new instance, then point `DATABASE_URL` (the
  `connections` secret) at it and restart the services.
- **Self-hosted:** `pg_dump --format=custom` on a schedule, and `pg_restore` into an empty
  database followed by `gpuwatch migrate`. A dump of a week of raw samples is large;
  `--exclude-table-data='gpu_samples_p*' --exclude-table-data='process_samples_p*'` keeps
  configuration, rollups and usage (costs and charts beyond the raw window survive) while
  skipping the raw partitions.
- Keep the environment secrets with the backup: without the same `API_KEY_PEPPER`, every
  API key, host token and enrolment token in the restored database stops working; without
  the same `LOCAL_MASTER_KEY` (or KMS key), webhook secrets cannot be opened.

## Scaling

- **API:** add replicas (ECS autoscaling between the min and max counts of each
  environment). With more than one API process, use Redis so the live view, rate limits
  and config invalidation are shared. Keep `WEB_CONCURRENCY=1` and scale tasks.
- **Database connections:** each process opens up to `DB_POOL_SIZE + DB_MAX_OVERFLOW`
  connections (30 by default). Keep `replicas x 30` below the RDS connection limit; the
  `db-connections` alarm warns at 80% of `db_max_connections`.
- **Worker:** one is enough for the default fleet sizes; a second adds availability. Locked
  jobs (rollup, alerts, insights) run on one worker at a time anyway; notifications are
  shared with `SKIP LOCKED`.
- **Ingest load:** proportional to GPUs divided by `GPUWATCH_INTERVAL_S`. A longer interval
  on the agents (for example 15 s) cuts write volume threefold at the cost of resolution.
  Measure with `make bench` against your own stack.

## Health checks

| Endpoint | Meaning |
| -------- | ------- |
| `GET /healthz` | Liveness: the process answers |
| `GET /readyz` | Readiness: 200 when Postgres answers (Redis is reported, `"status": "degraded"` when it is down); 503 when Postgres does not |
| `GET /api/v1/system` | Configuration summary for signed-in users: cloud, key mode, storage, cache backend, mail mode, retention, active keys, Redis check |

The ALB target group uses `/healthz`; Compose uses `/healthz` for the api container.

## Prometheus

The API's `/metrics` serves GPUWatch's own metrics and one gauge per GPU for the whole
fleet (`gpuwatch_gpu_up`, `gpuwatch_gpu_utilization_percent`,
`gpuwatch_gpu_memory_used_bytes`, `gpuwatch_gpu_memory_total_bytes`,
`gpuwatch_gpu_temperature_celsius`, `gpuwatch_gpu_power_watts`, `gpuwatch_gpu_fan_percent`,
`gpuwatch_gpu_sm_clock_hertz`, `gpuwatch_gpu_processes`, labelled `host`, `gpu`, `uuid`,
`model`). A metric a GPU does not report is omitted, never 0. Set `METRICS_TOKEN` and
scrape with it:

```yaml
scrape_configs:
  - job_name: gpuwatch
    scheme: https
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials_file: /etc/prometheus/gpuwatch-metrics-token
    static_configs:
      - targets: ["gpuwatch.example.com"]
```

Each API replica serves its own process counters (ingest batches, rows, drops, latency),
so scrape through the load balancer for the fleet gauges and sum counters across scrapes,
or scrape tasks directly if you run service discovery inside the VPC. The worker serves
job metrics (`gpuwatch_job_seconds`, `gpuwatch_job_failures_total`,
`gpuwatch_notifications_total`, `gpuwatch_alerts_total`, `gpuwatch_insights_total`) on port
`WORKER_METRICS_PORT` (9464), reachable on AWS only from `worker_metrics_cidrs`.

Useful series:

| Question | Series |
| -------- | ------ |
| Are agents getting through? | `rate(gpuwatch_ingest_batches_total{outcome="accepted"}[5m])`, and `outcome="rate_limited"` or `"too_large"` |
| Is data being refused? | `rate(gpuwatch_ingest_dropped_total[5m])` by `reason` (`time_window`, `unknown_gpu`) |
| Is Redis failing silently? | `rate(gpuwatch_dependency_errors_total[5m])` |
| Is a worker job failing? | `rate(gpuwatch_job_failures_total[15m])` by `job` |
| Are alerts reaching people? | `rate(gpuwatch_notifications_total{outcome="failed"}[1h])` |

## Alarms

The `observability` module creates CloudWatch alarms to an SNS topic (with an optional
e-mail subscription, `alarm_email`): load balancer and per-service 5xx and unhealthy
targets, api p95 response time above `api_p95_latency_seconds`, ECS CPU and memory, RDS
CPU, free storage and connections, cache memory, failed worker jobs (from the worker log's
`job failed` lines) and failed alert deliveries (`notification failed`). A dashboard named by the
`dashboard_name` output shows the same signals.

## Logs

JSON lines on stdout: `ts`, `level`, `logger`, `msg`, `request_id` and fields. On AWS they
go to CloudWatch log groups per service. Useful filters:

- `"job failed"` (worker): a background job raised; the `job` field names it.
- `"notification failed"` (worker): with `channel` and `error`.
- `"mail not delivered (MAIL_MODE=log)"`: email is configured to the log only.
- `"alert fired"` (worker): with `rule`, `target` and `value`.
- `"request"` lines with `status` 5xx (API).

Agent batches, probes and scrapes are logged only when they fail.

## Rotating secrets

| Secret | How | Effect |
| ------ | --- | ------ |
| `SESSION_SECRET` | Replace the value (the `app` secret on AWS) and restart api tasks | Every dashboard session ends; users sign in again. Keys and tokens keep working |
| `API_KEY_PEPPER` | Replace and restart | **Every API key, host token and enrolment token stops working**: agents get `invalid_host_token` and re-enrol with their enrolment token (create new enrolment tokens first, since old ones stop working too); scripts need new API keys. Rotate only after a suspected leak |
| `METRICS_TOKEN` | Replace, restart api tasks, update Prometheus | Scrapes with the old token get 401 |
| `LOCAL_MASTER_KEY` | Only with `KEY_MODE=local`: replace, restart, then re-enter each webhook secret in Alerts, Channels | Old sealed secrets cannot be opened; deliveries fail until re-entered |
| KMS key | Automatic yearly rotation of the CMK keeps old ciphertexts readable | None |
| Database password, cache AUTH token | Rotate in RDS or ElastiCache, update the `connections` secret, restart | Brief reconnect |
| Webhook signing secret | Edit the channel and enter a new secret; update the receiver | Receivers must accept the new secret |

## Revoking hosts, tokens and keys

- **A decommissioned or compromised machine:** Hosts, the host's **Revoke** button
  (`POST /api/v1/hosts/{id}/revoke`). Its token is refused at once (on other replicas
  within about a second), its history stays, and its alerts resolve. If the agent still has
  a usable enrolment token it will re-enrol, so revoke that token too.
- **An enrolment token:** Hosts, Enrolment tokens, **Revoke**. No new machine can enrol;
  hosts already enrolled keep reporting.
- **An API key:** API keys, **Revoke**. Refused on the next request.
- **A GPU taken out of service:** once it shows as lost, the GPU page offers **Retire**
  (`PATCH /api/v1/gpus/{id}` with `{"retired": true}`). It leaves the fleet, its "GPU lost"
  alert resolves, and it comes back by itself if it reports again.
- **A user:** Users, disable them (owners only). Their sessions end immediately.

Every one of these is in the audit log.

## Re-attributing costs with workload rules

Workload rules map processes to workloads and teams. A new or changed rule applies to
hours rolled up from then on. To apply the current rules to recent history:

- Costs, Workload rules, **Apply to recent history**, or
- `POST /api/v1/workload-rules/apply` as an admin.

This queues one recompute range per host covering the last `RAW_RETENTION_DAYS`; the
worker's rollup job recomputes attribution for those hours over the next ticks (watch
`gpuwatch_job_seconds{job="rollup"}`). Hours older than the raw retention keep the
attribution they had. Rates need no re-attribution: they apply to all history at read
time.

## Users and owners

- Owners create users and change roles; at least one active owner always remains.
- Lost the last owner password? Run `gpuwatch create-owner --email ...` against the
  database (`make admin` locally, `make aws-admin` on AWS). It resets the password, makes
  the user an owner and ends their sessions.

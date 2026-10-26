# `observability` module

CloudWatch for a deployment: the app log groups, alarms to one SNS topic and a dashboard.

- **Log groups** `/gpuwatch/<name_prefix>/{api,worker,web,migrate}`, KMS-encrypted, with retention. The `service` module writes to them (`log_group_names` output).
- **Alarms** (SNS, optional e-mail subscription):
  - 5xx from each load-balanced app and from the load balancer itself
  - api **p95** time to first byte (`api_p95_latency_seconds`, 1.5 s by default: agent ingest and dashboard reads answer in milliseconds when healthy, so a slow p95 almost always means the database)
  - unhealthy targets, CPU and memory per ECS service
  - database CPU, free storage, connections
  - cache memory per node (the cache evicts LRU entries: live view tiles and rate-limit windows) and engine CPU
  - **worker job failures**: a metric filter turns the worker's JSON log lines `{"msg": "job failed", "job": ...}` into `GPUWatch/<name_prefix>/WorkerJobFailures`; failed jobs mean stale rollups and costs, unevaluated alerts or retention falling behind (alarm when above `worker_job_failures_threshold` for two 5-minute periods)
  - **notification failures**: `{"msg": "notification failed", "channel": ...}` becomes `NotificationFailures`; an alert email (SES) or webhook that could not be delivered alarms when above `notification_failures_threshold` in 5 minutes
- **Dashboard** with requests and errors, api latency p50/p95/p99, per-service CPU/memory, worker job and notification failures, database and cache.

Prometheus `/metrics` on the api (fleet, ingest and alert metrics; protected by `METRICS_TOKEN`) and on the worker (port 9464) remains the detailed source; CloudWatch covers what an on-call engineer needs without a Prometheus server. GPU fleet alerts themselves (a GPU too hot, a host offline) are GPUWatch's own job: its alert rules notify through its channels, not through this topic.

Not applied in `local-floci`: locally logs go to stdout and metrics to `/metrics`.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. | `string` | required |
| `log_retention_days` | App log retention. | `number` | `30` |
| `logs_kms_key_arn` | CMK for the log groups. | `string` | `null` |
| `alarm_email` | Alarm e-mail subscription. | `string` | `null` |
| `alb_arn_suffix` | Load balancer ARN suffix. | `string` | required |
| `ecs_cluster_name` | ECS cluster name. | `string` | required |
| `lb_services` | Service module `services` (must contain `api`). | `map(object)` | required |
| `ecs_services` | Service module `service_names`. | `map(string)` | required |
| `db_instance_identifier` | RDS instance identifier. | `string` | required |
| `db_max_connections` | Connection ceiling for the alarm. | `number` | `200` |
| `cache_replication_group_id` | ElastiCache replication group id. | `string` | required |
| `cache_node_count` | Nodes in the replication group. | `number` | `1` |
| `target_5xx_threshold` | 5xx per 5 minutes that alarm. | `number` | `25` |
| `api_p95_latency_seconds` | api p95 alarm threshold in seconds. | `number` | `1.5` |
| `worker_job_failed_log_pattern` | Filter pattern for failed worker jobs. | `string` | `{ $.msg = "job failed" }` |
| `worker_job_failures_threshold` | Failed jobs per 5 minutes (two periods running) that alarm. | `number` | `0` |
| `notification_failed_log_pattern` | Filter pattern for failed notification deliveries. | `string` | `{ $.msg = "notification failed" }` |
| `notification_failures_threshold` | Failed deliveries per 5 minutes that alarm. | `number` | `0` |

## Outputs

| Name | Description |
|---|---|
| `log_group_names` | Log group per app. |
| `alarm_topic_arn` | SNS topic receiving every alarm. |
| `dashboard_name` | CloudWatch dashboard. |
| `metrics_namespace` | Namespace of the log-derived metrics (`WorkerJobFailures`, `NotificationFailures`). |

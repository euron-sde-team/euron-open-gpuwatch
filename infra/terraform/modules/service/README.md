# `service` module

The application plane on ECS Fargate behind one Application Load Balancer.

| App | Image / command | Traffic | Task role |
|---|---|---|---|
| `api` | api image, `gpuwatch serve --host 0.0.0.0 --port 8080` | ALB paths `/api/*`, `/ingest/*`, `/healthz`, `/readyz`, `/health`, `/docs`, `/docs/*`, `/openapi.json` and `/metrics` | reports bucket, KMS seal/unseal of webhook secrets |
| `web` | web image (Next.js standalone, proxies `/api` to the api) | ALB default action: every other path | none |
| `worker` | api image, `gpuwatch worker`: rollups, cost attribution, alert evaluation, notification delivery (email, webhooks), insights, retention | none (Prometheus on 9464 only from `worker_metrics_cidrs`, if set) | reports bucket, KMS seal/unseal, SES send as the alert identity |
| `migrate` | api image, `gpuwatch migrate` (task definition only) | none | reports bucket, KMS seal/unseal |

The `migrate` task definition is also how an operator runs `seed-demo` or `create-owner` (a command override on `aws ecs run-task`; the `run_task` output has every parameter).

**Load balancer.** HTTP answers with a 301 to HTTPS; HTTPS uses `ELBSecurityPolicy-TLS13-1-2-2021-06` and drops invalid header fields. Agents on GPU machines need only outbound HTTPS: they post metric batches to `https://<hostname>/ingest/v1/...` with their host token as a bearer token. Listener rules (at most five path patterns per condition, so two rules) send `/api/*`, `/ingest/*`, `/healthz`, `/readyz`, `/health`, `/docs`, `/docs/*` and `/openapi.json` to the api target group; the default action sends everything else to the dashboard. An optional Route53 alias points `hostname` at it.

**`/metrics`.** It lists every host and GPU, so it is always forwarded to the api but protected twice: the api answers it only with `Authorization: Bearer <METRICS_TOKEN>` when that token is set (the AWS environments generate it in the `secrets` module), and with `metrics_allowed_cidrs` the load balancer forwards it only from those scrapers and answers a 404 to everyone else. The worker's own metrics (port 9464) never pass the load balancer; an in-VPC Prometheus reaches them directly through `worker_metrics_cidrs`.

**WAF** (`enable_waf`). AWS managed common, known-bad-inputs and IP-reputation rule sets plus a per-IP flood guard. The body-inspecting rules of the common set (`SizeRestrictions_BODY`, `CrossSiteScripting_BODY`, `GenericLFI_BODY`, `GenericRFI_BODY`) only count: ingest batches are JSON far above the 8 KB body limit and carry process command lines and file paths, so blocking on them would drop legitimate metric batches. The per-IP limit is high because many GPU hosts can share one NAT address. WAF logs redact `authorization` (host tokens, API keys), `cookie` and `x-api-key`.

**Least privilege.**

- One security group per app. Ingress only from the load balancer on the container port (none for `worker` and `migrate`); egress HTTPS (AWS APIs, ECR, webhook receivers) plus PostgreSQL and Redis for the apps that use them. The database and cache security groups get matching ingress rules, so access is granted per security group, never by CIDR.
- Execution role per app: pull, log, and `secretsmanager:GetSecretValue` on exactly the secrets listed in `secrets` (plus `kms:Decrypt` via Secrets Manager).
- Task role for `api`, `worker`, `migrate`: `s3:PutObject`/`GetObject`/`DeleteObject` on `reports/*` in the reports bucket, `s3:ListBucket` on the bucket, `kms:GenerateDataKey`/`Decrypt` only via S3, and `kms:Encrypt`/`Decrypt` only when the encryption context has exactly the key `gpuwatch:record` with a `channel:*` value, which is what the sealer always sends for a webhook signing secret. The `worker` alone also gets `ses:SendEmail`/`SendRawEmail` on `mail_send_resource_arns` (the alert sender identity and its configuration set). `web` has an empty task role.
- Read-only root filesystem; only `/tmp` (and `/app/.next/cache` for `web`) is writable. ARM64, no public IP, `initProcessEnabled`, 45 s stop timeout for the api's graceful drain (120 s for the worker to finish the job in hand).

**Deploys.** Circuit breaker with automatic rollback. `api` and `web` roll 100/200 % and autoscale on CPU; the `worker` is replaced (0/100 %): overlap would be safe (every job takes a Postgres advisory lock), but replacing keeps a deploy from doubling its database connections.

Not applied in `local-floci`: locally the same images run as Compose services.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Deployment prefix (at most 24 characters). | `string` | required |
| `vpc_id` | VPC. | `string` | required |
| `public_subnet_ids` | Subnets for the load balancer. | `list(string)` | required |
| `private_subnet_ids` | Subnets for the tasks. | `list(string)` | required |
| `hostname` | Public host name. | `string` | required |
| `certificate_arn` | ACM certificate for the HTTPS listener. | `string` | required |
| `route53_zone_id` | Zone for the alias record; null skips it. | `string` | `null` |
| `api_image` | api image (also worker and migrate). | `string` | required |
| `web_image` | web image. | `string` | required |
| `container_port` | Port api and web listen on. | `number` | `8080` |
| `environment` | Plain environment for api, worker, migrate. | `map(string)` | `{}` |
| `web_environment` | Plain environment for web. | `map(string)` | `{}` |
| `secrets` | ECS `secrets` entries (secrets module `ecs_secrets`). | `list(object)` | `[]` |
| `kms_key_arn` | CMK for webhook secret sealing, the reports bucket and secrets. | `string` | required |
| `reports_bucket_arn` | Reports bucket ARN. | `string` | required |
| `mail_send_resource_arns` | SES identity and configuration set the worker may send as (email module). Empty: no SES permission. | `list(string)` | `[]` |
| `db_security_group_id` / `db_port` | Database access. | `string` / `number` | required / `5432` |
| `cache_security_group_id` / `cache_port` | Cache access. | `string` / `number` | required / `6379` |
| `log_group_names` | Log group per app (observability module). | `map(string)` | required |
| `logs_kms_key_arn` | CMK for the WAF log group. | `string` | `null` |
| `cpu_architecture` | `ARM64` or `X86_64`. | `string` | `"ARM64"` |
| `container_insights` | `enabled`, `enhanced` or `disabled`. | `string` | `"enabled"` |
| `api_cpu`, `api_memory`, `api_min_count`, `api_max_count` | api sizing. | `number` | `1024`, `2048`, `2`, `6` |
| `worker_cpu`, `worker_memory`, `worker_count` | worker sizing. | `number` | `512`, `1024`, `1` |
| `web_cpu`, `web_memory`, `web_min_count`, `web_max_count` | web sizing. | `number` | `512`, `1024`, `1`, `3` |
| `cpu_target_percent` | Autoscaling CPU target. | `number` | `60` |
| `idle_timeout` | Load balancer idle timeout (s). | `number` | `60` |
| `deletion_protection` | Protect the load balancer. | `bool` | `true` |
| `access_logs_bucket` | Bucket for ALB access logs; null disables. | `string` | `null` |
| `metrics_allowed_cidrs` | Who may read `/metrics` through the ALB. Empty: anyone with `METRICS_TOKEN`. | `list(string)` | `[]` |
| `webhook_egress` | Extra worker egress as `{ cidr, port }` for webhook receivers not on HTTPS 443 (tasks reach only 443 by default). | `list(object)` | `[]` |
| `worker_metrics_cidrs` | In-VPC Prometheus CIDRs allowed to scrape the worker's `/metrics` directly (the worker has no load balancer). Empty: no worker ingress. | `list(string)` | `[]` |
| `worker_metrics_port` | Worker metrics port; matches `WORKER_METRICS_PORT`. | `number` | `9464` |
| `enable_waf` | Attach the WAF web ACL. | `bool` | `true` |
| `waf_rate_limit_per_5min` | Per-IP flood guard. | `number` | `20000` |
| `waf_log_retention_days` | WAF log retention. | `number` | `30` |

## Outputs

| Name | Description |
|---|---|
| `cluster_name`, `cluster_arn` | ECS cluster. |
| `url` | `https://<hostname>`. |
| `alb_dns_name` | CNAME target when the zone is not in Route53. |
| `alb_arn_suffix` | For CloudWatch metrics. |
| `services` | `{ api, web } => { service_name, target_group_arn_suffix }` (observability input). |
| `service_names` | `{ api, worker, web } => service name`. |
| `security_group_ids` | Task security group per app. |
| `task_role_arns` | Task role per app. |
| `run_task` | Cluster, task definition, container, subnets and security group for one-off CLI tasks. |

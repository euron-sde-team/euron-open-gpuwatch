# `cache` module

ElastiCache replication group (Valkey by default, Redis OSS accepted) in private subnets, for the fleet live view (latest sample per GPU), per-key and per-host rate-limit windows and config invalidation between replicas. Optional: without it each API process keeps its own, which is correct for a single replica only.

- TLS in transit (`transit_encryption_mode = required`) and a generated AUTH token, stored in Secrets Manager (`<name_prefix>/cache-auth`, JSON `AUTH_TOKEN` + `REDIS_URL`) and handed to the `secrets` module as the sensitive `connection_url` (`rediss://:<token>@<primary>:6379/0`).
- At rest encrypted with the CMK; slow log shipped to CloudWatch Logs.
- `maxmemory-policy = allkeys-lru` by default: every entry is rebuilt from Postgres or from the next agent batch, so a full cache evicts the least recently used and never loses data.
- With `num_cache_clusters >= 2`, automatic failover and Multi-AZ are on.

Not applied in `local-floci`: locally the cache is the `redis:7.4-alpine` Compose container (append-only file on).

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. | `string` | required |
| `vpc_id` | VPC id. | `string` | required |
| `subnet_ids` | Private subnets (2+ AZs for failover). | `list(string)` | required |
| `kms_key_arn` | CMK for data at rest and the AUTH token secret. | `string` | required |
| `logs_kms_key_arn` | CMK for the slow-log group. | `string` | `null` |
| `engine` | `valkey` or `redis`. | `string` | `"valkey"` |
| `engine_version` | Engine version. | `string` | `"8.0"` |
| `parameter_group_family` | Family matching the engine, e.g. `valkey8`, `redis7`. | `string` | `"valkey8"` |
| `maxmemory_policy` | Eviction policy. | `string` | `"allkeys-lru"` |
| `node_type` | Node type. | `string` | `"cache.t4g.small"` |
| `num_cache_clusters` | 1 (no failover) or 2+ (Multi-AZ failover). | `number` | `2` |
| `snapshot_retention_days` | Daily snapshots kept (0 disables). | `number` | `1` |
| `recovery_window_in_days` | Recovery window of the AUTH token secret. | `number` | `30` |
| `log_retention_days` | Slow-log retention. | `number` | `30` |
| `apply_immediately` | Apply modifications now instead of in the maintenance window. | `bool` | `false` |

## Outputs

| Name | Description |
|---|---|
| `primary_endpoint_address` | Primary endpoint hostname. |
| `replication_group_id` | Replication group id. |
| `member_clusters` | Node ids (CloudWatch `CacheClusterId`). |
| `security_group_id` | Consumers add ingress rules against it. |
| `auth_secret_arn` | Secret holding `AUTH_TOKEN` and `REDIS_URL`. |
| `connection_url` | Sensitive `REDIS_URL`, for the `secrets` module. |

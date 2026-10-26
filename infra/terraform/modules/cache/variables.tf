variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
}

variable "vpc_id" {
  description = "VPC id."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnets for the cache subnet group (2+ AZs for failover)."
  type        = list(string)
}

variable "kms_key_arn" {
  description = "CMK for data at rest and for the AUTH token secret."
  type        = string
}

variable "logs_kms_key_arn" {
  description = "CMK for the slow-log group. Null uses CloudWatch's default encryption."
  type        = string
  default     = null
}

variable "engine" {
  description = "valkey (default, cheaper) or redis."
  type        = string
  default     = "valkey"
  validation {
    condition     = contains(["valkey", "redis"], var.engine)
    error_message = "engine must be valkey or redis."
  }
}

variable "engine_version" {
  description = "Engine version, e.g. 8.0 for Valkey or 7.1 for Redis OSS."
  type        = string
  default     = "8.0"
}

variable "parameter_group_family" {
  description = "Parameter group family matching engine and engine_version, e.g. valkey8 or redis7."
  type        = string
  default     = "valkey8"
}

variable "maxmemory_policy" {
  description = "Eviction policy. allkeys-lru: Redis holds only the live view (rebuilt from the next ingest batch), rate-limit counters and config invalidation stamps (sessions and samples live in Postgres), so under memory pressure the oldest go first, costing at worst a stale live tile for one agent interval or a briefly relaxed rate limit."
  type        = string
  default     = "allkeys-lru"
}

variable "node_type" {
  description = "Node type. Graviton (t4g/m7g/r7g) recommended."
  type        = string
  default     = "cache.t4g.small"
}

variable "num_cache_clusters" {
  description = "Nodes in the replication group: 1 (no failover) or 2+ (primary plus replicas, Multi-AZ failover)."
  type        = number
  default     = 2
  validation {
    condition     = var.num_cache_clusters >= 1 && var.num_cache_clusters <= 6
    error_message = "num_cache_clusters must be between 1 and 6."
  }
}

variable "snapshot_retention_days" {
  description = "Daily snapshots kept (0 disables). Counters rehydrate from Postgres, so snapshots only speed up recovery."
  type        = number
  default     = 1
}

variable "recovery_window_in_days" {
  description = "Days a deleted AUTH token secret stays recoverable. 0 deletes immediately."
  type        = number
  default     = 30
}

variable "log_retention_days" {
  description = "Slow-log retention in CloudWatch Logs."
  type        = number
  default     = 30
}

variable "apply_immediately" {
  description = "Apply modifications now instead of in the maintenance window."
  type        = bool
  default     = false
}

# ElastiCache (Valkey by default, Redis OSS also accepted) for what GPUWatch shares
# between replicas: the fleet live view (latest sample per GPU, short TTL), per-key and
# per-host ingest rate-limit windows and config invalidation. All of it is optional:
# without Redis each process keeps its own (correct for one single-process replica).
#
#   - private subnets only, ingress added per consumer security group
#   - TLS in transit and an AUTH token; at rest encrypted with the CMK
#   - the token lives in Secrets Manager; the full REDIS_URL is handed to the
#     secrets module and injected into the tasks, never put in plain environment
resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-cache"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "cache" {
  name        = "${var.name_prefix}-cache"
  description = "Redis/Valkey; ingress only from application security groups"
  vpc_id      = var.vpc_id
  tags        = { Name = "${var.name_prefix}-cache" }
}

# Everything in this cache can be recomputed, so the least recently used entries are
# evicted when it fills up: a full cache costs hit rate, never correctness.
resource "aws_elasticache_parameter_group" "this" {
  name   = "${var.name_prefix}-cache"
  family = var.parameter_group_family

  parameter {
    name  = "maxmemory-policy"
    value = var.maxmemory_policy
  }
}

# Alphanumeric only: ElastiCache AUTH tokens forbid several symbols, and the token is
# embedded in the REDIS_URL without escaping.
resource "random_password" "auth" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "auth" {
  #checkov:skip=CKV2_AWS_57:The AUTH token rotates with `terraform apply -replace=module.cache.random_password.auth` (ElastiCache supports a rolling ROTATE strategy); no Lambda.
  name                    = "${var.name_prefix}/cache-auth"
  description             = "ElastiCache AUTH token and connection URL"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days
}

resource "aws_secretsmanager_secret_version" "auth" {
  secret_id = aws_secretsmanager_secret.auth.id
  secret_string = jsonencode({
    AUTH_TOKEN = random_password.auth.result
    REDIS_URL  = local.redis_url
  })
}

resource "aws_cloudwatch_log_group" "slow" {
  #checkov:skip=CKV_AWS_338:Retention is an input (log_retention_days); aws-prod keeps 365 days.
  name              = "/gpuwatch/${var.name_prefix}/cache-slow-log"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_kms_key_arn
}

resource "aws_elasticache_replication_group" "this" {
  #checkov:skip=CKV2_AWS_50:Multi-AZ failover is on whenever num_cache_clusters >= 2 (aws-prod); aws-dev runs one node for cost.
  replication_group_id = "${var.name_prefix}-cache"
  description          = "${var.name_prefix}: result cache, rate limits, config version"
  engine               = var.engine
  engine_version       = var.engine_version
  node_type            = var.node_type
  port                 = 6379
  parameter_group_name = aws_elasticache_parameter_group.this.name

  # One primary plus (num_cache_clusters - 1) replicas. Failover needs a replica.
  num_cache_clusters         = var.num_cache_clusters
  automatic_failover_enabled = var.num_cache_clusters > 1
  multi_az_enabled           = var.num_cache_clusters > 1

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.cache.id]

  at_rest_encryption_enabled = true
  kms_key_id                 = var.kms_key_arn
  transit_encryption_enabled = true
  transit_encryption_mode    = "required"
  auth_token                 = random_password.auth.result
  auth_token_update_strategy = "ROTATE"

  snapshot_retention_limit   = var.snapshot_retention_days
  snapshot_window            = "02:00-03:00"
  maintenance_window         = "sun:05:30-sun:06:30"
  auto_minor_version_upgrade = true
  apply_immediately          = var.apply_immediately

  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.slow.name
    destination_type = "cloudwatch-logs"
    log_format       = "json"
    log_type         = "slow-log"
  }
}

locals {
  # rediss:// = TLS. Database 0; the API keeps every key family under its own prefix.
  redis_url = "rediss://:${random_password.auth.result}@${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/0"
}

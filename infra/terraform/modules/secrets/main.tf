# The API's secrets, in Secrets Manager. ECS injects each JSON key into the api, worker
# and migrate containers as an environment variable; the values never appear in a task
# definition, a plan diff or a log.
#
# Three secrets with different lifecycles:
#
#   <name_prefix>/app          SESSION_SECRET, API_KEY_PEPPER. Generated once, then
#                              rotated out of band; Terraform never rolls them back.
#   <name_prefix>/metrics      METRICS_TOKEN (optional). The bearer token /metrics then
#                              requires; give the same value to your Prometheus scraper.
#   <name_prefix>/connections  DATABASE_URL, REDIS_URL. Derived from the database and
#                              cache modules and kept in step with them on every apply.
#
# SESSION_SECRET and API_KEY_PEPPER are distinct on purpose (the API refuses to boot if
# they are equal): rotating dashboard sessions must not invalidate every API key hash
# (agent enrolment and ingest keys included).
locals {
  app_keys        = ["API_KEY_PEPPER", "SESSION_SECRET"]
  metrics_keys    = var.include_metrics_token ? ["METRICS_TOKEN"] : []
  connection_keys = var.include_connection_urls ? ["DATABASE_URL", "REDIS_URL"] : []
}

resource "random_password" "this" {
  for_each = toset(local.app_keys)
  length   = 64
  special  = false
}

resource "aws_secretsmanager_secret" "app" {
  #checkov:skip=CKV2_AWS_57:These are HMAC keys; rotation is an operator procedure (docs/guides/operations.md), not a Lambda.
  name                    = "${var.name_prefix}/app"
  description             = "GPUWatch signing secrets (dashboard sessions, API key pepper)"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({ for k, v in random_password.this : k => v.result })

  # Rotation happens out of band (put a new version by hand or by pipeline). Without
  # this, the next `terraform apply` would quietly roll every secret back.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "random_password" "metrics" {
  count   = var.include_metrics_token ? 1 : 0
  length  = 48
  special = false
}

# A secret of its own, not a key in `app`: `app` ignores changes after creation, so a
# token switched on later would never reach it.
resource "aws_secretsmanager_secret" "metrics" {
  #checkov:skip=CKV2_AWS_57:A static bearer token shared with the Prometheus scraper; rotation is an operator procedure (docs/guides/operations.md), not a Lambda.
  count                   = var.include_metrics_token ? 1 : 0
  name                    = "${var.name_prefix}/metrics"
  description             = "GPUWatch /metrics bearer token (METRICS_TOKEN)"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days
}

resource "aws_secretsmanager_secret_version" "metrics" {
  count         = var.include_metrics_token ? 1 : 0
  secret_id     = aws_secretsmanager_secret.metrics[0].id
  secret_string = jsonencode({ METRICS_TOKEN = random_password.metrics[0].result })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "connections" {
  #checkov:skip=CKV2_AWS_57:Derived values; they change when the database or cache module rotates its credential.
  count                   = var.include_connection_urls ? 1 : 0
  name                    = "${var.name_prefix}/connections"
  description             = "GPUWatch connection URLs (PostgreSQL, Redis/Valkey)"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days
}

resource "aws_secretsmanager_secret_version" "connections" {
  count     = var.include_connection_urls ? 1 : 0
  secret_id = aws_secretsmanager_secret.connections[0].id
  secret_string = jsonencode({
    DATABASE_URL = var.database_url
    REDIS_URL    = var.redis_url
  })
}

locals {
  ecs_secrets = concat(
    [for k in local.app_keys : { name = k, valueFrom = "${aws_secretsmanager_secret.app.arn}:${k}::" }],
    [for k in local.metrics_keys : { name = k, valueFrom = "${aws_secretsmanager_secret.metrics[0].arn}:${k}::" }],
    [for k in local.connection_keys : { name = k, valueFrom = "${aws_secretsmanager_secret.connections[0].arn}:${k}::" }],
  )
}

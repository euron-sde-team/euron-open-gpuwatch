# The GPUWatch application plane on ECS Fargate, behind one Application Load
# Balancer:
#
#   api      agent ingest (/ingest/*), dashboard and REST API     ALB, autoscaled
#            (/api/*), probes, /docs, /openapi.json, /metrics
#   web      Next.js dashboard, every other path                  ALB, autoscaled
#   worker   rollups, cost attribution, alert evaluation,         no ingress, except
#            notification delivery (SES email, webhooks),         Prometheus on
#            insights, retention and partition upkeep             WORKER_METRICS_PORT from
#                                                                 worker_metrics_cidrs
#   migrate  one-off task definition (no service) for `gpuwatch migrate`, and with a
#            command override for `seed-demo` and `create-owner`
#
# Every app gets the same hardened shape:
#
#   - its own security group: ingress only from the load balancer (none for worker and
#     migrate), egress only to HTTPS and, when it needs them, PostgreSQL and Redis
#   - its own execution role (pull, log, inject the listed secrets) and task role
#     (api, worker, migrate: the reports bucket and KMS sealing of webhook secrets;
#     worker also: SES SendEmail as the alert sender identity; web: none)
#   - a read-only root filesystem with only the paths it must write mounted writable,
#     ARM64, no public IP, deployment circuit breaker with automatic rollback
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  region = data.aws_region.current.region

  api_health = ["CMD", "python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:${var.container_port}/healthz', timeout=3).status == 200 else 1)"]
  web_health = ["CMD", "node", "-e", "fetch('http://127.0.0.1:${var.container_port}/').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"]

  # One map drives security groups, roles, task definitions and services. The api image
  # carries the `gpuwatch` CLI as its entrypoint, so commands are subcommands.
  apps = {
    api = {
      image          = var.api_image
      command        = ["serve", "--host", "0.0.0.0", "--port", tostring(var.container_port)]
      service        = true
      load_balanced  = true
      app_env        = true
      runtime_policy = true
      database       = true
      cache          = true
      cpu            = var.api_cpu
      memory         = var.api_memory
      min_count      = var.api_min_count
      max_count      = var.api_max_count
      health         = local.api_health
      writable_paths = ["/tmp"]
    }
    worker = {
      image          = var.api_image
      command        = ["worker"]
      service        = true
      load_balanced  = false
      app_env        = true
      runtime_policy = true
      database       = true
      cache          = true
      cpu            = var.worker_cpu
      memory         = var.worker_memory
      min_count      = var.worker_count
      max_count      = var.worker_count
      health         = null
      writable_paths = ["/tmp"]
    }
    web = {
      image          = var.web_image
      command        = null
      service        = true
      load_balanced  = true
      app_env        = false
      runtime_policy = false
      database       = false
      cache          = false
      cpu            = var.web_cpu
      memory         = var.web_memory
      min_count      = var.web_min_count
      max_count      = var.web_max_count
      health         = local.web_health
      writable_paths = ["/tmp", "/app/.next/cache"]
    }
    migrate = {
      image          = var.api_image
      command        = ["migrate"]
      service        = false
      load_balanced  = false
      app_env        = true
      runtime_policy = true
      database       = true
      cache          = true
      cpu            = 512
      memory         = 1024
      min_count      = 0
      max_count      = 0
      health         = null
      writable_paths = ["/tmp"]
    }
  }

  services      = { for k, a in local.apps : k => a if a.service }
  load_balanced = { for k, a in local.apps : k => a if a.load_balanced }
  with_database = { for k, a in local.apps : k => a if a.database }
  with_cache    = { for k, a in local.apps : k => a if a.cache }
  with_secrets  = { for k, a in local.apps : k => a if a.app_env && length(var.secrets) > 0 }
  scaled        = { for k, a in local.services : k => a if a.max_count > a.min_count }

  app_environment = [for k, v in merge({ PORT = tostring(var.container_port) }, var.environment) : { name = k, value = v }]
  web_environment = [for k, v in merge({ PORT = tostring(var.container_port), HOSTNAME = "0.0.0.0" }, var.web_environment) : { name = k, value = v }]

  secret_arns = distinct([for s in var.secrets : regex("^(arn:[^:]+:secretsmanager:[^:]+:[^:]+:secret:[^:]+)", s.valueFrom)[0]])

  # Paths the api serves, in groups of at most five (the ALB limit per path_pattern
  # condition). Agents post metric batches to /ingest/v1/*; the dashboard (through the
  # web proxy) and API clients use /api/v1/*. /metrics is handled by its own rules below.
  api_paths = {
    100 = ["/api/*", "/ingest/*", "/healthz", "/readyz", "/health"]
    101 = ["/docs", "/docs/*", "/openapi.json"]
  }
}

# ─── Cluster ─────────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "this" {
  name = var.name_prefix
  setting {
    name  = "containerInsights"
    value = var.container_insights
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = ["FARGATE"]
  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

# ─── Load balancer ───────────────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb"
  description = "HTTPS into the load balancer"
  vpc_id      = var.vpc_id
  tags        = { Name = "${var.name_prefix}-alb" }
}

resource "aws_vpc_security_group_ingress_rule" "alb_public" {
  #checkov:skip=CKV_AWS_260:Port 80 only answers with a 301 to HTTPS (see the http listener).
  for_each          = toset(["80", "443"])
  security_group_id = aws_security_group.alb.id
  description       = "HTTP/HTTPS from the internet (80 only redirects)"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.key)
  to_port           = tonumber(each.key)
}

resource "aws_lb" "this" {
  #checkov:skip=CKV_AWS_150:Deletion protection is an input (deletion_protection); aws-prod enables it.
  #checkov:skip=CKV2_AWS_28:A WAF web ACL is attached below when enable_waf is true (both AWS environments).
  #checkov:skip=CKV2_AWS_76:The web ACL below includes AWSManagedRulesKnownBadInputsRuleSet (Log4JRCE, verified by CKV_AWS_192); this graph check cannot follow the enable_waf-gated association.
  #checkov:skip=CKV_AWS_91:Access logging is opt-in via access_logs_bucket (the bucket needs an ELB log-delivery policy the operator owns).
  name                       = "${var.name_prefix}-alb"
  load_balancer_type         = "application"
  internal                   = false
  subnets                    = var.public_subnet_ids
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
  # Every GPUWatch request is short (an ingest batch, a rollup query, a CSV export); the
  # idle timeout only needs to cover the slowest report export.
  idle_timeout               = var.idle_timeout
  enable_deletion_protection = var.deletion_protection

  dynamic "access_logs" {
    for_each = var.access_logs_bucket == null ? [] : [1]
    content {
      bucket  = var.access_logs_bucket
      prefix  = "alb"
      enabled = true
    }
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_target_group" "this" {
  #checkov:skip=CKV_AWS_378:TLS terminates at the load balancer; the hop to the task stays inside private subnets.
  for_each             = local.load_balanced
  name                 = substr("${var.name_prefix}-${each.key}", 0, 32)
  port                 = var.container_port
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = var.vpc_id
  deregistration_delay = 30
  health_check {
    # Liveness, not readiness: the api keeps serving through a Redis blip (the live view
    # and rate limits fall back), so a dependency outage must not pull every task out of
    # the load balancer.
    path                = each.key == "api" ? "/healthz" : "/"
    matcher             = "200-399"
    interval            = 15
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

# Everything not claimed by a rule below is the dashboard.
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this["web"].arn
  }
}

resource "aws_lb_listener_rule" "api" {
  for_each     = local.api_paths
  listener_arn = aws_lb_listener.https.arn
  priority     = tonumber(each.key)
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this["api"].arn
  }
  condition {
    path_pattern {
      values = each.value
    }
  }
}

# Prometheus /metrics names every host and GPU in the fleet. It is always routed to the
# api, which answers it only with "Authorization: Bearer <METRICS_TOKEN>" when the token
# is set (the AWS environments always generate one). With metrics_allowed_cidrs the
# load balancer also forwards it only from the listed scrapers; everyone else gets a 404
# from the load balancer itself.
resource "aws_lb_listener_rule" "metrics" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this["api"].arn
  }
  condition {
    path_pattern {
      values = ["/metrics"]
    }
  }
  dynamic "condition" {
    for_each = length(var.metrics_allowed_cidrs) > 0 ? [1] : []
    content {
      source_ip {
        values = var.metrics_allowed_cidrs
      }
    }
  }
}

resource "aws_lb_listener_rule" "metrics_denied" {
  count        = length(var.metrics_allowed_cidrs) > 0 ? 1 : 0
  listener_arn = aws_lb_listener.https.arn
  priority     = 20
  action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Not found"
      status_code  = "404"
    }
  }
  condition {
    path_pattern {
      values = ["/metrics"]
    }
  }
}

resource "aws_route53_record" "this" {
  count   = var.route53_zone_id == null ? 0 : 1
  zone_id = var.route53_zone_id
  name    = var.hostname
  type    = "A"
  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}

# ─── WAF ─────────────────────────────────────────────────────────────────────

# Managed rules with one deliberate exception: agent ingest batches are JSON bodies far
# above the common rule set's 8 KB body limit, and they carry process command lines,
# file paths and inference server labels, so the body-inspecting rules of the common
# rule set only count. Blocking them would drop legitimate metric batches; the api's
# schema validation, MAX_BODY_BYTES and per-host ingest rate limits are the controls that
# understand a batch.
resource "aws_wafv2_web_acl" "this" {
  count = var.enable_waf ? 1 : 0
  name  = "${var.name_prefix}-alb"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "common"
    priority = 10
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
        dynamic "rule_action_override" {
          for_each = toset(["SizeRestrictions_BODY", "CrossSiteScripting_BODY", "GenericLFI_BODY", "GenericRFI_BODY"])
          content {
            name = rule_action_override.value
            action_to_use {
              count {}
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-common"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "known-bad-inputs"
    priority = 20
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "ip-reputation"
    priority = 30
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAmazonIpReputationList"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-ip-reputation"
      sampled_requests_enabled   = true
    }
  }

  # A coarse flood guard per source IP. The api's own limits (INGEST_RPM_PER_HOST per
  # host token, DEFAULT_RPM_LIMIT per API key) are the real rate limits; this only keeps
  # a flood from reaching the tasks at all. Many GPU hosts can share one NAT address.
  rule {
    name     = "rate-per-ip"
    priority = 40
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = var.waf_rate_limit_per_5min
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-rate-per-ip"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name_prefix}-alb"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "this" {
  count        = var.enable_waf ? 1 : 0
  resource_arn = aws_lb.this.arn
  web_acl_arn  = aws_wafv2_web_acl.this[0].arn
}

resource "aws_cloudwatch_log_group" "waf" {
  #checkov:skip=CKV_AWS_338:Retention is an input (waf_log_retention_days); aws-prod keeps 365 days.
  count             = var.enable_waf ? 1 : 0
  name              = "aws-waf-logs-${var.name_prefix}"
  retention_in_days = var.waf_log_retention_days
  kms_key_id        = var.logs_kms_key_arn
}

resource "aws_wafv2_web_acl_logging_configuration" "this" {
  count                   = var.enable_waf ? 1 : 0
  resource_arn            = aws_wafv2_web_acl.this[0].arn
  log_destination_configs = [aws_cloudwatch_log_group.waf[0].arn]
  # Host tokens, API keys and dashboard sessions never reach a log.
  redacted_fields {
    single_header {
      name = "authorization"
    }
  }
  redacted_fields {
    single_header {
      name = "cookie"
    }
  }
  redacted_fields {
    single_header {
      name = "x-api-key"
    }
  }
}

# ─── Task networking ─────────────────────────────────────────────────────────

resource "aws_security_group" "task" {
  for_each    = local.apps
  name        = "${var.name_prefix}-${each.key}-task"
  description = "${each.key} tasks; ingress only from the load balancer, if at all"
  vpc_id      = var.vpc_id
  tags        = { Name = "${var.name_prefix}-${each.key}-task" }
}

resource "aws_vpc_security_group_ingress_rule" "from_lb" {
  for_each                     = local.load_balanced
  security_group_id            = aws_security_group.task[each.key].id
  description                  = "From the load balancer"
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = var.container_port
  to_port                      = var.container_port
}

# The worker has no load balancer; an in-VPC Prometheus scrapes its /metrics directly.
resource "aws_vpc_security_group_ingress_rule" "worker_metrics" {
  for_each          = toset(var.worker_metrics_cidrs)
  security_group_id = aws_security_group.task["worker"].id
  description       = "Prometheus scrape of worker /metrics"
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = var.worker_metrics_port
  to_port           = var.worker_metrics_port
}

resource "aws_vpc_security_group_egress_rule" "lb_to_task" {
  for_each                     = local.load_balanced
  security_group_id            = aws_security_group.alb.id
  description                  = "To ${each.key} tasks"
  referenced_security_group_id = aws_security_group.task[each.key].id
  ip_protocol                  = "tcp"
  from_port                    = var.container_port
  to_port                      = var.container_port
}

resource "aws_vpc_security_group_egress_rule" "https" {
  for_each          = local.apps
  security_group_id = aws_security_group.task[each.key].id
  description       = "HTTPS to AWS APIs (S3, KMS, SES, Secrets Manager), ECR and webhook endpoints"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

# Webhook receivers on other ports (an internal chat relay or incident tool on 8080):
# opt in per port and destination; nothing beyond HTTPS is open by default. Only the
# worker delivers notifications, so only the worker gets these rules.
resource "aws_vpc_security_group_egress_rule" "webhooks" {
  for_each          = { for e in var.webhook_egress : "${e.cidr}:${e.port}" => e }
  security_group_id = aws_security_group.task["worker"].id
  description       = "Webhook receivers on port ${each.value.port}"
  cidr_ipv4         = each.value.cidr
  ip_protocol       = "tcp"
  from_port         = each.value.port
  to_port           = each.value.port
}

resource "aws_vpc_security_group_egress_rule" "db" {
  for_each                     = local.with_database
  security_group_id            = aws_security_group.task[each.key].id
  description                  = "To PostgreSQL"
  referenced_security_group_id = var.db_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
}

resource "aws_vpc_security_group_ingress_rule" "db_from_task" {
  for_each                     = local.with_database
  security_group_id            = var.db_security_group_id
  description                  = "From ${each.key} tasks"
  referenced_security_group_id = aws_security_group.task[each.key].id
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
}

resource "aws_vpc_security_group_egress_rule" "cache" {
  for_each                     = local.with_cache
  security_group_id            = aws_security_group.task[each.key].id
  description                  = "To Redis/Valkey"
  referenced_security_group_id = var.cache_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = var.cache_port
  to_port                      = var.cache_port
}

resource "aws_vpc_security_group_ingress_rule" "cache_from_task" {
  for_each                     = local.with_cache
  security_group_id            = var.cache_security_group_id
  description                  = "From ${each.key} tasks"
  referenced_security_group_id = aws_security_group.task[each.key].id
  ip_protocol                  = "tcp"
  from_port                    = var.cache_port
  to_port                      = var.cache_port
}

# ─── IAM ─────────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

# Execution role: pull the image, write logs, inject the listed secrets. Nothing else.
resource "aws_iam_role" "execution" {
  for_each           = local.apps
  name               = "${var.name_prefix}-${each.key}-execution"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  for_each   = local.apps
  role       = aws_iam_role.execution[each.key].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution" {
  count = length(var.secrets) > 0 ? 1 : 0
  statement {
    sid       = "InjectSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = local.secret_arns
  }
  statement {
    sid       = "DecryptSecrets"
    actions   = ["kms:Decrypt"]
    resources = [var.kms_key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${local.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "execution" {
  for_each = local.with_secrets
  name     = "secrets"
  role     = aws_iam_role.execution[each.key].id
  policy   = data.aws_iam_policy_document.execution[0].json
}

# Task role: exactly what the api, worker and CLI code does at runtime.
data "aws_iam_policy_document" "runtime" {
  # Cost report exports: the api writes and serves reports/<id>.csv, the worker's
  # retention deletes expired ones.
  statement {
    sid       = "ReportObjects"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
    resources = ["${var.reports_bucket_arn}/reports/*"]
  }
  # Without ListBucket a missing object answers 403 instead of 404.
  statement {
    sid       = "ReportBucket"
    actions   = ["s3:ListBucket"]
    resources = [var.reports_bucket_arn]
  }
  # SSE-KMS on the reports bucket: only through S3.
  statement {
    sid       = "ReportEncryption"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = [var.kms_key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${local.region}.amazonaws.com"]
    }
  }
  # Webhook signing secret sealing (core/sealing.py): direct Encrypt (api, when a channel
  # is saved) and Decrypt (worker, to sign a delivery), only with the encryption context
  # the sealer always sends, {"gpuwatch:record": "channel:<channel id>"}, and no other key.
  statement {
    sid       = "SealWebhookSecrets"
    actions   = ["kms:Encrypt", "kms:Decrypt"]
    resources = [var.kms_key_arn]
    condition {
      test     = "ForAllValues:StringEquals"
      variable = "kms:EncryptionContextKeys"
      values   = ["gpuwatch:record"]
    }
    condition {
      test     = "StringLike"
      variable = "kms:EncryptionContext:gpuwatch:record"
      values   = ["channel:*"]
    }
  }
}

# Alert email: the worker delivers every notification, so only its task role may send,
# and only as the configured SES identity (email module send_resource_arns).
data "aws_iam_policy_document" "mail" {
  count = length(var.mail_send_resource_arns) > 0 ? 1 : 0
  statement {
    sid       = "SendAlertMail"
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = var.mail_send_resource_arns
  }
}

resource "aws_iam_role" "task" {
  for_each           = local.apps
  name               = "${var.name_prefix}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy" "task" {
  for_each = { for k, a in local.apps : k => a if a.runtime_policy }
  name     = "runtime"
  role     = aws_iam_role.task[each.key].id
  policy   = data.aws_iam_policy_document.runtime.json
}

resource "aws_iam_role_policy" "mail" {
  count  = length(var.mail_send_resource_arns) > 0 ? 1 : 0
  name   = "mail"
  role   = aws_iam_role.task["worker"].id
  policy = data.aws_iam_policy_document.mail[0].json
}

# ─── Task definitions ────────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "this" {
  for_each                 = local.apps
  family                   = "${var.name_prefix}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution[each.key].arn
  task_role_arn            = aws_iam_role.task[each.key].arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }

  dynamic "volume" {
    for_each = toset(each.value.writable_paths)
    content {
      name = trim(replace(volume.value, "/", "-"), "-.")
    }
  }

  container_definitions = jsonencode([{
    name                   = each.key
    image                  = each.value.image
    essential              = true
    readonlyRootFilesystem = true
    command                = each.value.command
    portMappings = (
      each.value.load_balanced ? [{ containerPort = var.container_port, protocol = "tcp" }] :
      each.key == "worker" && length(var.worker_metrics_cidrs) > 0 ? [{ containerPort = var.worker_metrics_port, protocol = "tcp" }] : []
    )
    environment     = each.value.app_env ? local.app_environment : local.web_environment
    secrets         = each.value.app_env ? var.secrets : []
    linuxParameters = { initProcessEnabled = true }
    # SIGTERM first: the api drains in-flight requests (uvicorn allows 30 s), the worker
    # finishes the job in hand. ECS waits longer than the drain before SIGKILL; a job cut
    # off anyway rolls back and runs again on the next tick (rollups are upserts).
    stopTimeout = each.key == "worker" ? 120 : 45
    mountPoints = [for p in each.value.writable_paths : { sourceVolume = trim(replace(p, "/", "-"), "-."), containerPath = p, readOnly = false }]
    healthCheck = each.value.health == null ? null : {
      command     = each.value.health
      interval    = 15
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = var.log_group_names[each.key]
        awslogs-region        = local.region
        awslogs-stream-prefix = each.key
      }
    }
  }])
}

# ─── Services + autoscaling ──────────────────────────────────────────────────

resource "aws_ecs_service" "this" {
  for_each               = local.services
  name                   = each.key
  cluster                = aws_ecs_cluster.this.arn
  task_definition        = aws_ecs_task_definition.this[each.key].arn
  desired_count          = each.value.min_count
  launch_type            = "FARGATE"
  enable_execute_command = false
  propagate_tags         = "SERVICE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.task[each.key].id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = each.value.load_balanced ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.this[each.key].arn
      container_name   = each.key
      container_port   = var.container_port
    }
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  # The worker is replaced, never doubled. Overlap would be safe (every job takes a
  # Postgres advisory lock or claims rows with SKIP LOCKED), but replacing keeps a deploy
  # from holding twice the worker's database connections.
  deployment_minimum_healthy_percent = each.value.load_balanced ? 100 : 0
  deployment_maximum_percent         = each.value.load_balanced ? 200 : 100
  health_check_grace_period_seconds  = each.value.load_balanced ? 30 : null

  # Autoscaling owns the running count after the first deploy.
  lifecycle {
    ignore_changes = [desired_count]
  }
  depends_on = [aws_lb_listener.https, aws_lb_listener_rule.api]
}

resource "aws_appautoscaling_target" "this" {
  for_each           = local.scaled
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.this[each.key].name}"
  min_capacity       = each.value.min_count
  max_capacity       = each.value.max_count
}

resource "aws_appautoscaling_policy" "cpu" {
  for_each           = aws_appautoscaling_target.this
  name               = "${var.name_prefix}-${each.key}-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = each.value.service_namespace
  scalable_dimension = each.value.scalable_dimension
  resource_id        = each.value.resource_id
  target_tracking_scaling_policy_configuration {
    target_value       = var.cpu_target_percent
    scale_in_cooldown  = 120
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

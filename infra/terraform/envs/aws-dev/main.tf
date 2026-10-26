# ─────────────────────────────────────────────────────────────────────────────
# aws-dev: a full, cheaper copy of production. Two AZs, single NAT, single-AZ
# database, one cache node, no deletion protection, small autoscaling ceilings.
#
# Validate-only in this repository (nothing is ever applied to a real account by
# the project itself); everything needed to deploy is here:
#   cp terraform.tfvars.example terraform.tfvars   # then edit
#   terraform init && terraform apply -target=module.ecr   # push images, then:
#   terraform apply
# ─────────────────────────────────────────────────────────────────────────────

module "kms" {
  source                  = "../../modules/kms"
  name_prefix             = var.name_prefix
  deletion_window_in_days = 7
}

module "network" {
  source                     = "../../modules/network"
  name_prefix                = var.name_prefix
  az_count                   = 2
  single_nat_gateway         = true
  enable_interface_endpoints = false
  logs_kms_key_arn           = module.kms.key_arn
  flow_log_retention_days    = 14
}

module "database" {
  source                = "../../modules/database"
  name_prefix           = var.name_prefix
  vpc_id                = module.network.vpc_id
  subnet_ids            = module.network.private_subnet_ids
  kms_key_arn           = module.kms.key_arn
  instance_class        = var.db_instance_class
  allocated_storage     = 20
  max_allocated_storage = 100
  multi_az              = false
  backup_retention_days = 3
  deletion_protection   = false
  skip_final_snapshot   = true
}

module "cache" {
  source                  = "../../modules/cache"
  name_prefix             = var.name_prefix
  vpc_id                  = module.network.vpc_id
  subnet_ids              = module.network.private_subnet_ids
  kms_key_arn             = module.kms.key_arn
  logs_kms_key_arn        = module.kms.key_arn
  node_type               = var.cache_node_type
  num_cache_clusters      = 1
  recovery_window_in_days = 0
  log_retention_days      = 14
  apply_immediately       = true
}

module "storage" {
  source        = "../../modules/storage"
  name_prefix   = var.name_prefix
  kms_key_arn   = module.kms.key_arn
  force_destroy = true
}

# The SES identity alert email is sent from. When its domain's zone is in Route53 (the
# hostname's zone by default, mail_route53_zone_id for another domain) the DKIM and MAIL
# FROM records are created too; otherwise publish the email_dns_records
# output. A new SES account must request production access before it can mail anyone
# who is not a verified address.
module "email" {
  source          = "../../modules/email"
  name_prefix     = var.name_prefix
  domain          = local.mail_domain
  from_local_part = var.mail_from_local_part
  manage_dns      = local.mail_zone_id != null
  route53_zone_id = local.mail_zone_id
  dmarc_policy    = var.mail_dmarc_policy
}

module "secrets" {
  source                  = "../../modules/secrets"
  name_prefix             = var.name_prefix
  kms_key_arn             = module.kms.key_arn
  include_metrics_token   = true
  recovery_window_in_days = 0
  include_connection_urls = true
  database_url            = module.database.connection_url
  redis_url               = module.cache.connection_url
}

module "ecr" {
  source       = "../../modules/ecr"
  name_prefix  = var.name_prefix
  kms_key_arn  = module.kms.key_arn
  force_delete = true
}

locals {
  url         = "https://${var.hostname}"
  mail_domain = coalesce(var.mail_from_domain, var.hostname)
  # The hostname's zone serves the default mail domain; another domain names its own.
  mail_zone_id = var.mail_from_domain == null ? var.route53_zone_id : var.mail_route53_zone_id

  # Everything the api, worker and migrate read that is not a secret (names as in
  # apps/api/src/gpuwatch/core/config.py). Secrets (SESSION_SECRET, API_KEY_PEPPER,
  # METRICS_TOKEN, DATABASE_URL, REDIS_URL) come from module.secrets.
  api_environment = merge({
    ENVIRONMENT    = "production"
    GPUWATCH_CLOUD = "aws"
    LOG_LEVEL      = "INFO"
    AWS_REGION     = var.region
    # Webhook signing secrets sealed with KMS, report exports in S3.
    KEY_MODE       = "kms"
    KMS_KEY_ID     = module.kms.alias_name
    STORAGE        = "s3"
    REPORTS_BUCKET = module.storage.bucket_name
    # Alert email through SES as the email module's identity; links point at the dashboard.
    MAIL_MODE     = "ses"
    MAIL_FROM     = module.email.from_address
    DASHBOARD_URL = local.url
    CORS_ORIGINS  = local.url
    COOKIE_SECURE = "true"
    # Webhooks to private addresses only when you opt in (see webhook_egress).
    WEBHOOK_ALLOW_PRIVATE = tostring(var.webhook_allow_private)
    # Trust X-Forwarded-For only from inside the VPC (the load balancer).
    FORWARDED_ALLOW_IPS = module.network.vpc_cidr_block
    # One uvicorn process per task (exact /metrics); scale with tasks. Pool sized so
    # (api_max_count + worker + migrate) x (pool + overflow) stays under db_max_connections.
    WEB_CONCURRENCY = "1"
    DB_POOL_SIZE    = "5"
    DB_MAX_OVERFLOW = "10"
  }, var.api_extra_environment)
}

module "service" {
  source             = "../../modules/service"
  name_prefix        = var.name_prefix
  vpc_id             = module.network.vpc_id
  public_subnet_ids  = module.network.public_subnet_ids
  private_subnet_ids = module.network.private_subnet_ids
  hostname           = var.hostname
  certificate_arn    = var.certificate_arn
  route53_zone_id    = var.route53_zone_id

  api_image = "${module.ecr.repository_urls["api"]}:${var.image_tag}"
  web_image = "${module.ecr.repository_urls["web"]}:${var.image_tag}"

  environment     = local.api_environment
  web_environment = { API_INTERNAL_URL = local.url }
  secrets         = module.secrets.ecs_secrets

  kms_key_arn             = module.kms.key_arn
  reports_bucket_arn      = module.storage.bucket_arn
  mail_send_resource_arns = module.email.send_resource_arns
  db_security_group_id    = module.database.security_group_id
  db_port                 = module.database.port
  cache_security_group_id = module.cache.security_group_id
  log_group_names         = module.observability.log_group_names
  logs_kms_key_arn        = module.kms.key_arn

  api_cpu       = 512
  api_memory    = 1024
  api_min_count = 1
  api_max_count = 2
  web_min_count = 1
  web_max_count = 2
  worker_count  = 1

  deletion_protection    = false
  enable_waf             = true
  waf_log_retention_days = 14
  metrics_allowed_cidrs  = var.metrics_allowed_cidrs
  worker_metrics_cidrs   = var.worker_metrics_cidrs
  webhook_egress         = var.webhook_egress
}

module "observability" {
  source             = "../../modules/observability"
  name_prefix        = var.name_prefix
  log_retention_days = 14
  logs_kms_key_arn   = module.kms.key_arn
  alarm_email        = var.alarm_email

  alb_arn_suffix   = module.service.alb_arn_suffix
  ecs_cluster_name = module.service.cluster_name
  lb_services      = module.service.services
  ecs_services     = module.service.service_names

  db_instance_identifier     = module.database.instance_identifier
  db_max_connections         = 100
  cache_replication_group_id = module.cache.replication_group_id
  cache_node_count           = 1
  api_p95_latency_seconds    = var.api_p95_latency_seconds
}

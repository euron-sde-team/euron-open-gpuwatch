variable "region" {
  description = "AWS region."
  type        = string
}

variable "environment" {
  description = "Environment tag."
  type        = string
  default     = "prod"
}

variable "extra_tags" {
  description = "Tags added to every resource."
  type        = map(string)
  default     = {}
}

variable "name_prefix" {
  description = "Prefix for every resource name (at most 24 characters); the reports bucket name derives from it, so make it globally unique (e.g. \"acme-gpuwatch-prod\")."
  type        = string
}

variable "hostname" {
  description = "Public host name of the deployment, e.g. gpuwatch.example.com."
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate in the same region covering hostname."
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone for the hostname alias record. Null: create the CNAME yourself (load_balancer_dns_name output)."
  type        = string
  default     = null
}

variable "image_tag" {
  description = "Image tag to deploy (the git commit or a release)."
  type        = string
}

variable "alarm_email" {
  description = "Alarm notification address."
  type        = string
  default     = null
}

variable "api_extra_environment" {
  description = "Extra api/worker/migrate environment (e.g. RAW_RETENTION_DAYS, HOST_OFFLINE_AFTER_S, INGEST_RPM_PER_HOST; see docs/guides/configuration.md). Never secrets."
  type        = map(string)
  default     = {}
}

variable "mail_from_domain" {
  description = "Domain verified in SES for alert email (sent as <mail_from_local_part>@<domain>). Null: the hostname, whose DNS records then go in route53_zone_id."
  type        = string
  default     = null
}

variable "mail_route53_zone_id" {
  description = "Hosted zone serving mail_from_domain, when that is set. Null: publish the email_dns_records output yourself."
  type        = string
  default     = null
}

variable "mail_from_local_part" {
  description = "Local part of the alert sender address."
  type        = string
  default     = "alerts"
}

variable "mail_dmarc_policy" {
  description = "DMARC policy to publish for the mail domain (none, quarantine, reject) when its zone is managed here. Null: no record (the parent domain's policy applies)."
  type        = string
  default     = null
}

variable "webhook_allow_private" {
  description = "Allow alert webhooks to private addresses (WEBHOOK_ALLOW_PRIVATE), e.g. an internal chat relay inside the VPC. Metadata and link-local addresses are refused regardless."
  type        = bool
  default     = false
}

variable "webhook_egress" {
  description = "Extra worker egress for webhook receivers not on HTTPS 443, as { cidr, port } pairs. Empty: HTTPS only."
  type = list(object({
    cidr = string
    port = number
  }))
  default = []
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.medium"
}

variable "cache_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.small"
}

variable "metrics_allowed_cidrs" {
  description = "Source CIDRs allowed to scrape /metrics through the load balancer. Empty: from anywhere, with the METRICS_TOKEN bearer token (secrets output metrics_token_secret_arn)."
  type        = list(string)
  default     = []
}

variable "worker_metrics_cidrs" {
  description = "In-VPC Prometheus CIDRs allowed to scrape the worker's /metrics on port 9464. Empty: no worker ingress."
  type        = list(string)
  default     = []
}

variable "api_p95_latency_seconds" {
  description = "api p95 response time (agent ingest and dashboard reads) that raises an alarm."
  type        = number
  default     = 1.5
}

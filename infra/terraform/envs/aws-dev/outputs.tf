output "url" {
  description = "Public URL: the dashboard; the REST API under /api/v1; agents set GPUWATCH_URL to this and post batches to /ingest/v1."
  value       = module.service.url
}

output "load_balancer_dns_name" {
  description = "CNAME target when the zone is not in Route53."
  value       = module.service.alb_dns_name
}

output "cluster_name" {
  description = "ECS cluster."
  value       = module.service.cluster_name
}

output "services" {
  description = "ECS service names."
  value       = module.service.service_names
}

output "ecr_repositories" {
  description = "Image repositories."
  value       = module.ecr.repository_urls
}

output "run_task" {
  description = "Parameters for one-off tasks (migrate, seed-demo, create-owner)."
  value       = module.service.run_task
}

output "reports_bucket" {
  description = "Report exports bucket (REPORTS_BUCKET)."
  value       = module.storage.bucket_name
}

output "mail_from" {
  description = "Sender of alert email (MAIL_FROM)."
  value       = module.email.from_address
}

output "email_dns_records" {
  description = "DKIM and MAIL FROM records to publish when the mail domain is not in route53_zone_id."
  value       = module.email.dns_records
}

output "metrics_token_secret_arn" {
  description = "Secrets Manager secret holding METRICS_TOKEN, the bearer token for scraping /metrics."
  value       = module.secrets.metrics_token_secret_arn
}

output "kms_key_alias" {
  description = "KMS key alias (KMS_KEY_ID)."
  value       = module.kms.alias_name
}

output "dashboard_name" {
  description = "CloudWatch dashboard."
  value       = module.observability.dashboard_name
}

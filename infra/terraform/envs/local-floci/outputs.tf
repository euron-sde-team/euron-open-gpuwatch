output "reports_bucket" {
  description = "REPORTS_BUCKET for the local stack."
  value       = module.storage.bucket_name
}

output "kms_key_alias" {
  description = "KMS_KEY_ID for the local stack."
  value       = module.kms.alias_name
}

output "app_secret_arn" {
  description = "The emulated Secrets Manager secret (SESSION_SECRET, API_KEY_PEPPER)."
  value       = module.secrets.secret_arn
}

output "mail_from" {
  description = "MAIL_FROM of the emulated SES identity (matches the compose default)."
  value       = module.email.from_address
}

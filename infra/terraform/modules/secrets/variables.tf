variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
}

variable "kms_key_arn" {
  description = "CMK that encrypts the secrets. Null uses the AWS-managed key."
  type        = string
  default     = null
}

variable "recovery_window_in_days" {
  description = "Days a deleted secret stays recoverable. 0 deletes immediately (local and throwaway environments)."
  type        = number
  default     = 30
}

variable "include_metrics_token" {
  description = "Generate METRICS_TOKEN in its own secret and inject it, so the API's /metrics requires \"Authorization: Bearer <token>\" (it lists hosts and GPUs)."
  type        = bool
  default     = false
}

# A boolean, not a null check on the URLs: those are unknown until apply, and count
# must be decidable at plan time.
variable "include_connection_urls" {
  description = "Create the connections secret from database_url and redis_url. false where Compose supplies them (local-floci)."
  type        = bool
  default     = false
}

variable "database_url" {
  description = "DATABASE_URL (database module connection_url), with include_connection_urls."
  type        = string
  default     = null
  sensitive   = true
}

variable "redis_url" {
  description = "REDIS_URL (cache module connection_url), with include_connection_urls."
  type        = string
  default     = null
  sensitive   = true
}

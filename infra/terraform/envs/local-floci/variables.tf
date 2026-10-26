variable "endpoint" {
  description = "Emulator endpoint. http://floci:4566 inside compose, http://localhost:4466 from the host."
  type        = string
  default     = "http://localhost:4466"
}

variable "name_prefix" {
  description = "Must match REPORTS_BUCKET (<name_prefix>-reports) and KMS_KEY_ID (alias/<name_prefix>) in deploy/compose/compose.floci.yaml."
  type        = string
  default     = "gpuwatch-local"
}

variable "cors_origins" {
  description = "Dashboard origins allowed to fetch report objects with JavaScript (none needed: downloads go through the API)."
  type        = list(string)
  default     = ["http://localhost:4410", "http://127.0.0.1:4410"]
}

variable "mail_domain" {
  description = "Domain of the emulated SES identity; matches MAIL_FROM (alerts@gpuwatch.local) in deploy/compose/compose.yaml."
  type        = string
  default     = "gpuwatch.local"
}

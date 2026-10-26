# ─────────────────────────────────────────────────────────────────────────────
# Local environment on the Floci AWS emulator.
#
# The modules that build production run here unchanged; only the provider endpoints
# differ. `make up` applies this automatically (the compose `terraform` one-shot)
# before migrate, api and worker start, so local development seals webhook signing
# secrets with KMS (alias/gpuwatch-local) and writes cost report exports to S3
# (gpuwatch-local-reports) exactly as AWS does, and the SES identity and Secrets
# Manager secret exist as they would there. By hand, against a running emulator:
#
#   terraform -chdir=infra/terraform/envs/local-floci init
#   terraform -chdir=infra/terraform/envs/local-floci apply -var endpoint=http://localhost:4466
#
# Postgres and Redis are plain Compose containers locally (the emulator does not back
# RDS or ElastiCache); the database and cache modules are exercised by aws-dev and
# aws-prod, which must validate cleanly.
# ─────────────────────────────────────────────────────────────────────────────

module "kms" {
  source                  = "../../modules/kms"
  name_prefix             = var.name_prefix
  deletion_window_in_days = 7
}

module "storage" {
  source        = "../../modules/storage"
  name_prefix   = var.name_prefix
  kms_key_arn   = module.kms.key_arn
  enforce_tls   = false # the emulator speaks plain HTTP
  force_destroy = true
  cors_origins  = var.cors_origins
}

# Generated secrets are an AWS-deployment concern; locally compose reads
# deploy/compose/.env (make env). Created here anyway so the module is exercised.
module "secrets" {
  source                  = "../../modules/secrets"
  name_prefix             = var.name_prefix
  kms_key_arn             = module.kms.key_arn
  recovery_window_in_days = 0
}

# The alert sender identity, verified the way it is on AWS: the emulator keeps a domain
# identity Pending until its DKIM CNAMEs exist in a Route53 zone, so the zone and the
# records are created here through the same email module production uses. The local
# stack still delivers alert email to Mailpit (MAIL_MODE=smtp); MAIL_MODE=ses with
# AWS_ENDPOINT_URL pointed at the emulator sends as this identity instead.
resource "aws_route53_zone" "mail" {
  #checkov:skip=CKV2_AWS_38:Emulator-only zone; never resolvable on the internet.
  #checkov:skip=CKV2_AWS_39:Emulator-only zone; there is no resolver to log.
  name          = var.mail_domain
  force_destroy = true
}

module "email" {
  source          = "../../modules/email"
  name_prefix     = var.name_prefix
  domain          = var.mail_domain
  manage_dns      = true
  route53_zone_id = aws_route53_zone.mail.zone_id
  dmarc_policy    = null
}

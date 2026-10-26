#!/usr/bin/env bash
# Plan, apply, re-plan and destroy the full aws-dev environment against a throwaway Floci.
#
# terraform validate cannot see plan-time and apply-time failures (unknown for_each keys,
# rejected arguments, broken references between modules). This runs the real production
# configuration against an AWS API without an AWS account. The repository is not touched:
# the Terraform tree is copied to a temp directory and a provider override is added there.
#
# Expected re-plan drift: Floci does not persist a few attributes (maintenance windows,
# transit encryption mode, log delivery, parameter group values, storage type, KMS rotation
# period, security groups on replication groups). Real AWS stores them all.
# Takes about five minutes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${TF_FLOCI_PORT:-4496}"
NAME="gpuwatch-tf-floci"
WORK="$(mktemp -d)"
TF_IMAGE="hashicorp/terraform:1.16.6"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -p "127.0.0.1:$PORT:4566" -e FLOCI_HOSTNAME=localhost floci/floci:2.3.0 >/dev/null
for _ in $(seq 1 60); do curl -sf -o /dev/null "http://localhost:$PORT/" && break; sleep 1; done

cp -R "$ROOT/infra/terraform" "$WORK/"
find "$WORK" -name ".terraform*" -prune -exec rm -rf {} +
ENV_DIR="$WORK/terraform/envs/aws-dev"

# The ALB listener needs a certificate: request one from Floci's ACM.
CERT_ARN="$(docker run --rm --add-host host.docker.internal:host-gateway \
  -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test -e AWS_DEFAULT_REGION=us-east-1 \
  amazon/aws-cli:2.31.18 --endpoint-url "http://host.docker.internal:$PORT" \
  acm request-certificate --domain-name gpuwatch-dev.example.com --validation-method DNS \
  --query CertificateArn --output text)"

cat > "$ENV_DIR/zz_floci_override.tf" <<'TF'
provider "aws" {
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
}
TF
cat > "$ENV_DIR/terraform.tfvars" <<TF
region          = "us-east-1"
name_prefix     = "gw-floci-dev"
hostname        = "gpuwatch-dev.example.com"
certificate_arn = "$CERT_ARN"
image_tag       = "0.1.0"
alarm_email     = "oncall@example.com"
TF

tf() {
  docker run --rm -v "$WORK/terraform:/infra" -w /infra/envs/aws-dev \
    --add-host host.docker.internal:host-gateway --add-host 000000000000.host.docker.internal:host-gateway \
    -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test -e AWS_REGION=us-east-1 \
    -e AWS_ENDPOINT_URL="http://host.docker.internal:$PORT" -e TF_IN_AUTOMATION=1 "$TF_IMAGE" "$@"
}

echo "== init";    tf init -input=false -no-color >/dev/null
echo "== plan";    tf plan -input=false -no-color -out=tfplan | grep -E "^Plan:"
echo "== apply";   tf apply -input=false -no-color -auto-approve tfplan | grep -E "^Apply complete"
echo "== re-plan (attributes Floci does not persist may show as updates; nothing may be added or replaced)"
REPLAN="$(tf plan -input=false -no-color)"
echo "$REPLAN" | grep -E "^Plan:|No changes" || true
if echo "$REPLAN" | grep -qE "must be replaced|Plan: [1-9][0-9]* to add"; then
  echo "re-plan wants to add or replace resources: the configuration does not converge" >&2
  exit 1
fi
# Floci backs ECR with a real registry container it can start only when given the Docker
# socket, which this script deliberately does not hand over. Without it, DeleteRepository
# fails with a ServerException and the provider retries forever, so ECR (whose creation was
# exercised above) is dropped from state before the destroy.
#
# Floci also refuses the call the provider uses to delete SES MAIL FROM attributes (a
# PutEmailIdentityMailFromAttributes with an empty MailFromDomain answers 400 there; AWS
# accepts it). Deleting the identity right after removes its attributes anyway, so that
# one resource is dropped from state too.
echo "== destroy (ECR and the SES MAIL FROM attributes left to the throwaway emulator, see comments)"
tf state rm module.ecr >/dev/null
tf state rm module.email.aws_sesv2_email_identity_mail_from_attributes.domain >/dev/null
tf destroy -input=false -no-color -auto-approve | grep -E "^Destroy complete"
echo "aws-dev: planned, applied, converged and destroyed against Floci"

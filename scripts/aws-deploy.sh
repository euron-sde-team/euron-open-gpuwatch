#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# One-shot deployment to AWS:  scripts/aws-deploy.sh <aws-dev|aws-prod> <image-tag>
#
#   1. terraform apply the image registries (and the KMS key that encrypts them)
#   2. build the api and web images for the cluster's CPU architecture and push them
#   3. terraform apply everything else with that image tag
#   4. run the database migrations as a one-off ECS task (its task definition comes from 3)
#   5. wait for the api, worker and web services to become stable
#
# Needs: terraform, docker (buildx), the AWS CLI, credentials for the target account,
# and infra/terraform/envs/<env>/terraform.tfvars (copy the .example next to it).
# This repository never runs it against a real account itself; it is here so you can.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
ENV="${1:?usage: aws-deploy.sh <aws-dev|aws-prod> <image-tag>}"
TAG="${2:?usage: aws-deploy.sh <aws-dev|aws-prod> <image-tag>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/infra/terraform/envs/$ENV"
PLATFORM="${PLATFORM:-linux/arm64}"   # matches the service module's default cpu_architecture

for bin in terraform docker aws python3; do command -v "$bin" >/dev/null || { echo "missing: $bin"; exit 1; }; done
[[ -f "$DIR/terraform.tfvars" ]] || { echo "create $DIR/terraform.tfvars from terraform.tfvars.example first"; exit 1; }
[[ -n "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ]] && echo "note: the working tree has uncommitted changes; the images are built from it as-is"

tf() { terraform -chdir="$DIR" "$@"; }
json() { python3 -c "import json,sys; print(json.load(sys.stdin)$1)"; }

echo "==> terraform init"
tf init -input=false >/dev/null

echo "==> 1/5 registries"
tf apply -input=false -auto-approve -var "image_tag=$TAG" -target=module.ecr

region="${AWS_REGION:-$(aws configure get region 2>/dev/null || true)}"
region="${region:-$(grep -E '^region' "$DIR/terraform.tfvars" | sed -E 's/.*"(.*)".*/\1/')}"
repos=$(tf output -json ecr_repositories)
api_repo=$(echo "$repos" | json "['api']")
web_repo=$(echo "$repos" | json "['web']")
aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "${api_repo%%/*}" >/dev/null

echo "==> 2/5 images ($TAG, $PLATFORM)"
docker buildx build --platform "$PLATFORM" -f "$ROOT/infra/docker/api.Dockerfile" -t "$api_repo:$TAG" --push "$ROOT/apps/api"
docker buildx build --platform "$PLATFORM" -f "$ROOT/infra/docker/web.Dockerfile" -t "$web_repo:$TAG" --push "$ROOT/apps/web"

echo "==> 3/5 infrastructure"
tf apply -input=false -auto-approve -var "image_tag=$TAG"

echo "==> 4/5 migrations"
"$ROOT/scripts/aws-run-task.sh" "$ENV" migrate

echo "==> 5/5 waiting for the services"
cluster=$(tf output -raw cluster_name)
services=$(tf output -json services | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin).values()))")
# shellcheck disable=SC2086 # one argument per service name
aws ecs wait services-stable --region "$region" --cluster "$cluster" --services $services

echo
echo "Deployed $TAG to $ENV: $(tf output -raw url)"
cat <<NEXT
Next, the first owner account:
  GPUWATCH_OWNER_PASSWORD='...' make aws-admin ENV=$ENV EMAIL=you@example.com
NEXT

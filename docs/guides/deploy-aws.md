# Deploy to AWS

The Terraform in `infra/terraform` describes a complete production deployment. The
maintainers develop and test against the local emulator only: nothing in this project has
been applied to a real AWS account. The AWS environments are kept valid
(`make tf-validate tf-lint tf-security`) on every change, and the whole `aws-dev`
environment is planned, applied, re-planned and destroyed against Floci
(`make tf-aws-on-floci`, see [testing.md](testing.md#infrastructure)). This guide describes
how you would apply it in your own account. Review the plan before you apply it. The
module-level overview, the topology diagram and the security posture are in
[infra/README.md](../../infra/README.md).

- [Environments](#environments)
- [What gets created](#what-gets-created)
- [Prerequisites](#prerequisites)
- [Variables](#variables)
- [One-command deploy](#one-command-deploy)
- [Step by step](#step-by-step)
- [First owner](#first-owner)
- [Alert email (SES)](#alert-email-ses)
- [Point the agents at the deployment](#point-the-agents-at-the-deployment)
- [Prometheus and the metrics token](#prometheus-and-the-metrics-token)
- [Upgrades](#upgrades)
- [Tearing down](#tearing-down)

## Environments

| Environment | What it is |
| ----------- | ---------- |
| `envs/local-floci` | Storage, KMS, secrets and the SES identity on the Floci emulator. Applied automatically by `make up` |
| `envs/aws-dev` | The full stack, cost-lean: two availability zones, a single NAT gateway, single-AZ RDS with 3-day backups, one cache node, api 1 to 2 tasks, web 1 to 2, one worker, no deletion protection, 14-day log retention |
| `envs/aws-prod` | The full stack, resilient: three availability zones with a NAT gateway each, VPC interface endpoints, Multi-AZ RDS with 14-day backups and more storage, a primary and replica cache with failover, api 2 to 8 tasks, web 2 to 4, deletion protection, a 30-day KMS deletion window and 365-day log retention |

## What gets created

| Module | Resources |
| ------ | --------- |
| `network` | VPC across two or three availability zones, public and private subnets, NAT, flow logs, an S3 gateway endpoint |
| `kms` | Customer-managed key with rotation (RDS, ElastiCache, S3, ECR, secrets, logs, webhook secret sealing) |
| `storage` | Private, TLS-only reports bucket, SSE-KMS, objects expire after 30 days (match `REPORT_RETENTION_DAYS`) |
| `secrets` | `SESSION_SECRET` and `API_KEY_PEPPER` (generated once, distinct), `METRICS_TOKEN`, and the database and cache URLs in Secrets Manager, injected by ECS |
| `email` | SES identity for the alert sender, DKIM and MAIL FROM records |
| `database` | RDS PostgreSQL 16 (encrypted, private, automated backups, `rds.force_ssl`) |
| `cache` | ElastiCache Valkey with TLS and an AUTH token |
| `ecr` | Repositories for the api and web images |
| `service` | ECS Fargate cluster; api, worker and web services behind one ALB with WAF; a task definition for one-off commands (migrate, create-owner) |
| `observability` | CloudWatch log groups, a dashboard and alarms to an SNS topic ([operations.md](operations.md#alarms)) |

The ALB sends `/api/*`, `/ingest/*`, `/healthz`, `/readyz`, `/health`, `/docs` and
`/openapi.json` to the api, `/metrics` to the api (optionally only from
`metrics_allowed_cidrs`), and everything else to the dashboard. The agent image is not
deployed by Terraform: agents run on your GPU machines.

The api, worker and migrate tasks run with `ENVIRONMENT=production`,
`GPUWATCH_CLOUD=aws`, `KEY_MODE=kms`, `STORAGE=s3`, `MAIL_MODE=ses`,
`COOKIE_SECURE=true`, `FORWARDED_ALLOW_IPS` set to the VPC CIDR,
`WEBHOOK_ALLOW_PRIVATE` from the variable of the same name, and the bucket, key alias,
sender, dashboard URL and CORS origin wired from the modules. Add other non-secret settings
from [configuration.md](configuration.md) through `api_extra_environment`.

## Prerequisites

- An AWS account and credentials for it in your shell (profile or SSO).
- Terraform 1.16, Docker with buildx, the AWS CLI and Python 3.
- An ACM certificate in the target region for the host name you will use.
- Optionally a Route53 hosted zone for that name (otherwise you create the DNS records
  yourself).

## Variables

Copy `terraform.tfvars.example` to `terraform.tfvars` (git-ignored) in the environment you
deploy, and optionally `backend.tf.example` to `backend.tf` for S3 state:

| Variable | Meaning |
| -------- | ------- |
| `region` | AWS region (example: `us-east-1`) |
| `name_prefix` | Prefix for every resource (at most 24 characters); the reports bucket name derives from it, so make it globally unique |
| `hostname` | Public host name, for example `gpuwatch.example.com` |
| `certificate_arn` | ACM certificate in the same region covering `hostname` |
| `route53_zone_id` | Optional: creates the alias record. Remove it and CNAME `hostname` to the `load_balancer_dns_name` output instead |
| `image_tag` | The tag the services run (example: `0.1.0`). `make aws-deploy` overrides it with its `TAG` |
| `mail_from_domain`, `mail_route53_zone_id`, `mail_from_local_part`, `mail_dmarc_policy` | Optional: the alert sender (default `alerts@<hostname>`) and where its DNS records go |
| `alarm_email` | Optional: e-mail subscription for alarms |
| `metrics_allowed_cidrs` | Optional: who may read `/metrics` through the ALB (it also needs the token) |
| `worker_metrics_cidrs` | Optional: in-VPC Prometheus CIDRs allowed to scrape the worker on port 9464 |
| `webhook_allow_private`, `webhook_egress` | Optional: allow webhooks to private addresses and extra egress for receivers not on HTTPS 443 (default: refused, HTTPS only) |
| `api_extra_environment` | Optional: extra non-secret API settings, for example `RAW_RETENTION_DAYS` or `HOST_OFFLINE_AFTER_S` |
| `db_instance_class`, `cache_node_type` | Defaults `db.t4g.small` and `cache.t4g.micro` |
| `api_p95_latency_seconds` | Alarm threshold for api p95 response time (default 1.5) |

Every module has a README under `infra/terraform/modules/` with its inputs and outputs.

## One-command deploy

```bash
make aws-deploy ENV=aws-dev TAG=0.1.0
```

[`scripts/aws-deploy.sh`](../../scripts/aws-deploy.sh) runs five steps:

1. `terraform apply -target=module.ecr` (the registries and the key that encrypts them);
2. builds the api and web images for `linux/arm64` (override with `PLATFORM`) and pushes
   them with the tag;
3. `terraform apply` of everything else with that image tag;
4. runs the migrations as a one-off ECS task (`make aws-migrate`);
5. waits until the api, worker and web services are stable, then prints the URL.

## Step by step

The same, by hand:

```bash
cd infra/terraform/envs/aws-dev
terraform init
terraform apply -target=module.ecr
# build and push both images with your image_tag (repositories from `terraform output ecr_repositories`)
docker buildx build --platform linux/arm64 -f ../../../docker/api.Dockerfile -t <api repo>:<tag> --push ../../../../apps/api
docker buildx build --platform linux/arm64 -f ../../../docker/web.Dockerfile -t <web repo>:<tag> --push ../../../../apps/web
terraform apply
cd -
make aws-migrate ENV=aws-dev
```

`make aws-migrate` (and `make aws-admin`) use
[`scripts/aws-run-task.sh`](../../scripts/aws-run-task.sh): it reads the `run_task`
output (cluster, task definition, subnets, security groups), starts a Fargate task with
the command as arguments to the `gpuwatch` CLI, waits for it, and prints its logs and exit
code.

## First owner

```bash
GPUWATCH_OWNER_PASSWORD='a-long-Passw0rd' make aws-admin ENV=aws-dev EMAIL=you@example.com
```

The password needs at least 10 characters, upper and lower case letters and a digit. It is
passed to the task as an environment override, not a command argument. Sign in at the
`url` output and add other users in Users.

## Alert email (SES)

- The `email` module creates the SES identity for the sender (`alerts@<hostname>` by
  default) with DKIM and a MAIL FROM domain. When the mail domain's zone is not managed by
  this Terraform, publish the `email_dns_records` output yourself.
- **Request SES production access** for the account and region. A sandboxed account only
  delivers to verified addresses, so alert email to your on-call list would fail (visible
  in Alerts, Deliveries, and as the notification failure alarm).
- Only the worker may send, and only as that identity (IAM).

## Point the agents at the deployment

Agents need only outbound HTTPS from the GPU machines to the ALB on 443.

1. Sign in, open Hosts, "Add a host", and create an enrolment token.
2. On each GPU machine, run the agent with `GPUWATCH_URL=https://<hostname>` (the `url`
   output, or `https://<load_balancer_dns_name>` if you have no DNS name yet; the
   certificate must then match, so prefer the host name) and the token
   ([agent guide](agent.md)).
3. The agent enrols at `/ingest/v1/enroll` and posts a batch every 5 s to
   `/ingest/v1/batches` with `Authorization: Bearer gwh_...`.

The WAF counts rather than blocks the body-inspecting managed rules on `/ingest/*`
(batches are large JSON); the api's per-host rate limit (`INGEST_RPM_PER_HOST`), body
limit and schema validation guard the route.

## Prometheus and the metrics token

`/metrics` lists every host and GPU, so the AWS environments generate a `METRICS_TOKEN`:

```bash
aws secretsmanager get-secret-value --secret-id "$(terraform -chdir=infra/terraform/envs/aws-dev output -raw metrics_token_secret_arn)" \
  --query SecretString --output text
```

Configure your Prometheus with that token as a bearer token for
`https://<hostname>/metrics`, and optionally restrict the path at the ALB with
`metrics_allowed_cidrs`. See [operations.md](operations.md#prometheus).

## Upgrades

```bash
make aws-deploy ENV=aws-dev TAG=0.1.1
```

New images, then `terraform apply`, then migrations, then a rolling replacement of the
services. Migrations are forward-only Alembic revisions; read the CHANGELOG before
upgrading across minor versions.

## Tearing down

`aws-dev` has no deletion protection: `terraform -chdir=infra/terraform/envs/aws-dev
destroy` removes everything (the bucket is force-destroyed). `aws-prod` keeps deletion
protection on the database and the load balancer and takes a final snapshot; turn
protection off deliberately before a destroy.

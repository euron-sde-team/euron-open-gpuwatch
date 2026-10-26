# Run locally against real AWS

`make up` runs everything against the Floci emulator. To check the AWS code paths against
real services (KMS, S3, SES) without deploying the containers, run the local stack with the
`compose.aws.yaml` overlay. Postgres, Redis, Mailpit and the dashboard stay local
containers; the api, worker and migrate containers talk to your AWS resources.

## 1. Create the resources

Apply `infra/terraform/envs/aws-dev` ([deploy-aws.md](deploy-aws.md)), or create your own:
a KMS key (or alias), an S3 bucket for reports, and a verified SES identity for the
sender. The containers need permission for `kms:Encrypt` and `kms:Decrypt` on the key,
`s3:PutObject`, `s3:GetObject` and `s3:DeleteObject` under `reports/` in the bucket, and
`ses:SendEmail` as the identity.

## 2. Configure

```bash
cp deploy/compose/.env.aws.example deploy/compose/.env.aws
```

Fill it in from `terraform output` in `infra/terraform/envs/aws-dev`:

| Variable | Value |
| -------- | ----- |
| `AWS_REGION` | The region of the resources |
| `AWS_PROFILE` | Optional: the profile to use (default `default`) |
| `REPORTS_BUCKET` | `reports_bucket` output |
| `KMS_KEY_ID` | `kms_key_alias` output |
| `MAIL_FROM` | A sender verified in SES (the `mail_from` output) |

`.env.aws` is git-ignored. It never holds credentials: the overlay mounts `~/.aws`
read-only into the containers and uses your profile through the standard AWS chain.

## 3. Start

```bash
make up-aws
```

This is `compose.yaml` plus `compose.aws.yaml`. The overlay sets, for migrate, api and
worker: `GPUWATCH_CLOUD=aws`, `STORAGE=s3`, `KEY_MODE=kms`, `MAIL_MODE=ses`, the profile
variables, and the values from `.env.aws`. `AWS_ENDPOINT_URL` is not set, so the SDK talks
to real AWS. There is no Floci and no Terraform container in this mode.

`make admin` and `make demo` address the Floci overlay, so in this mode create an owner by
running the CLI through the AWS overlay directly:

```bash
docker compose --env-file deploy/compose/.env -f deploy/compose/compose.yaml \
  -f deploy/compose/compose.aws.yaml exec api gpuwatch create-owner --email you@example.com
```

Then create a channel, send a test (SES), add a webhook with a secret (sealed with your KMS
key) and export a cost report (written to your bucket) from the dashboard. To feed data,
point an agent at `http://localhost:4430` with an enrolment token ([agent.md](agent.md)).

## Notes

- **SES sandbox:** until the account has production access, SES delivers only to verified
  addresses. Use a verified recipient on the demo channel, or expect delivery failures in
  Alerts, Deliveries.
- **Costs:** KMS requests, S3 storage and SES messages are billed to your account.
- **Credentials:** the containers run as UID 10001 and read `~/.aws/config` and
  `~/.aws/credentials` through the read-only mount, so those files must be readable by
  that user. A profile with static or role-based credentials in those files is the
  simplest setup.
- **Stopping:** `make down` stops this stack too. It deletes the local volumes, not your
  AWS resources.

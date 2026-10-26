# `secrets` module

Everything the API must not receive as plain configuration, in Secrets Manager, encrypted with the CMK. ECS injects each JSON key as an environment variable through the task execution role.

| Secret | Keys | Lifecycle |
|---|---|---|
| `<name_prefix>/app` | `SESSION_SECRET`, `API_KEY_PEPPER` | 64 random characters each, generated once. Rotated out of band; `ignore_changes` keeps Terraform from rolling a rotation back. |
| `<name_prefix>/metrics` | `METRICS_TOKEN` | 48 random characters, generated once, only with `include_metrics_token = true`. The API then answers `/metrics` only with `Authorization: Bearer <token>`; read the value from this secret for your Prometheus scrape config. |
| `<name_prefix>/connections` | `DATABASE_URL`, `REDIS_URL` | Taken from the `database` and `cache` modules' `connection_url` outputs and updated on every apply. Only with `include_connection_urls = true`. |

The two signing values are distinct on purpose (the API refuses to boot in production if they are equal): rotating dashboard sessions must not invalidate every API key hash (agent enrolment and ingest keys included).

Applied in `local-floci` with `include_connection_urls = false`: Compose supplies the connection URLs and `deploy/compose/.env` the signing values (`make env`); the secret is created anyway so the module is exercised on every `make up`.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. | `string` | required |
| `kms_key_arn` | CMK that encrypts the secrets. Null uses the AWS-managed key. | `string` | `null` |
| `recovery_window_in_days` | Days a deleted secret stays recoverable. 0 deletes immediately. | `number` | `30` |
| `include_metrics_token` | Create and inject `METRICS_TOKEN`. | `bool` | `false` |
| `include_connection_urls` | Create the connections secret. | `bool` | `false` |
| `database_url` | Sensitive `DATABASE_URL`. | `string` | `null` |
| `redis_url` | Sensitive `REDIS_URL`. | `string` | `null` |

## Outputs

| Name | Description |
|---|---|
| `secret_arn` | The `app` secret. |
| `metrics_token_secret_arn` | The `metrics` secret, or null. |
| `connections_secret_arn` | The `connections` secret, or null. |
| `keys` | Every environment variable the secrets provide. |
| `ecs_secrets` | Ready-made ECS `secrets` entries (`<arn>:<key>::`). |

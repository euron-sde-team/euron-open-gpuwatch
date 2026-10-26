# `kms` module

One customer-managed KMS key (annual rotation) plus alias. It seals every webhook signing secret before it reaches Postgres (KMS `Encrypt` with EncryptionContext `gpuwatch:record=channel:<channel id>`, so a sealed value copied to another channel row fails to open; the worker `Decrypt`s it with the same context to sign a delivery) and encrypts the reports bucket, RDS, ElastiCache, Secrets Manager and CloudWatch logs. Usage is granted per role by IAM, scoped by `kms:EncryptionContextKeys` or `kms:ViaService`.

Applied in `local-floci`: the alias `alias/gpuwatch-local` is what the API uses with `KEY_MODE=kms`.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. The alias is `alias/<name_prefix>`. | `string` | required |
| `deletion_window_in_days` | Waiting period before a scheduled key deletion completes. | `number` | `30` |
| `admin_principal_arns` | IAM principals allowed to administer (not use) the key. Empty = account root only, which delegates to IAM policies. | `list(string)` | `[]` |

## Outputs

| Name | Description |
|---|---|
| `key_arn` | KMS key ARN. |
| `key_id` | KMS key id. |
| `alias_name` | Alias, usable as KMS_KEY_ID. |

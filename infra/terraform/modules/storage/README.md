# `storage` module

One private S3 bucket, `<name_prefix>-reports`, for cost and usage report exports. The API writes each generated CSV to `reports/<report id>.csv` with SSE-KMS and streams it back on download; the database row keeps only the object key. The worker deletes reports older than `REPORT_RETENTION_DAYS` (30 by default) together with their objects.

- Public access blocked, bucket-owner-enforced ownership, TLS-only bucket policy (`aws:SecureTransport`).
- Default encryption SSE-KMS with the CMK (bucket key on), SSE-S3 when no key is given.
- Lifecycle: objects under `reports/` expire after `expiration_days` (30, matching `REPORT_RETENTION_DAYS`) as a backstop to the worker's own cleanup; incomplete multipart uploads abort after a day. Reports can be regenerated from the rollups, so the bucket is not versioned.
- Optional CORS (`cors_origins`), only for JavaScript fetches from the dashboard; downloads go through the API, so none is needed by default.

Applied in `local-floci` as `gpuwatch-local-reports` (the `REPORTS_BUCKET` in `deploy/compose/compose.floci.yaml`) with `enforce_tls = false` (the emulator speaks plain HTTP) and `force_destroy = true`.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. The bucket is `<name_prefix>-reports`. | `string` | required |
| `kms_key_arn` | CMK for SSE-KMS. Null falls back to SSE-S3. | `string` | `null` |
| `enforce_tls` | Deny any request not made over TLS. | `bool` | `true` |
| `expiration_days` | Days a report export is kept. | `number` | `30` |
| `cors_origins` | Browser origins allowed to GET objects with JavaScript. Empty = no CORS. | `list(string)` | `[]` |
| `force_destroy` | Allow destroying a non-empty bucket. Never in production. | `bool` | `false` |

## Outputs

| Name | Description |
|---|---|
| `bucket_name` | Reports bucket name (`REPORTS_BUCKET`). |
| `bucket_arn` | Reports bucket ARN, for IAM policies. |

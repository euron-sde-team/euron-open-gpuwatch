# `email` module

The SES (v2) sending identity for alert email. The worker delivers every email notification (an alert firing or resolving, a channel test from the dashboard) with SESv2 `SendEmail`, `MAIL_MODE=ses` and `MAIL_FROM` set to the `from_address` output; the `service` module grants `ses:SendEmail`/`SendRawEmail` to the worker task role on `send_resource_arns` only (this identity and its configuration set), so no other task can send and the worker cannot send as anyone else.

- A domain identity with Easy DKIM, attached to a configuration set that requires TLS to the receiving mail server, records reputation metrics and suppresses addresses that bounced or complained.
- A custom MAIL FROM subdomain (`bounce.<domain>`), so SPF aligns with the sending domain.
- With `manage_dns`, the three DKIM CNAMEs, the MAIL FROM MX and SPF records and (unless `dmarc_policy` is null) a DMARC record in `route53_zone_id`. Otherwise publish the `dns_records` output by hand.

A new SES account is in the sandbox and can only mail verified addresses: request production access before relying on alert email (docs/guides/deploy-aws.md). Failed deliveries show up in the worker log as `notification failed` and raise the `observability` module's notification failure alarm.

Applied in `local-floci` for `gpuwatch.local` together with an emulator-only Route53 zone, so the identity verifies the way it does on AWS (Floci keeps a domain identity Pending until its DKIM CNAMEs exist). The local stack still sends alert email to Mailpit (`MAIL_MODE=smtp`).

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. | `string` | required |
| `domain` | Sending domain verified in SES. | `string` | required |
| `from_local_part` | Local part of the sender address. | `string` | `"alerts"` |
| `from_name` | Display name of the sender. | `string` | `"GPUWatch"` |
| `mail_from_subdomain` | Custom MAIL FROM subdomain. | `string` | `"bounce"` |
| `manage_dns` | Create the DNS records in `route53_zone_id`. | `bool` | `false` |
| `route53_zone_id` | Zone serving the domain (with `manage_dns`). | `string` | `null` |
| `dmarc_policy` | DMARC policy to publish; null skips the record. | `string` | `"none"` |
| `dmarc_report_address` | DMARC aggregate-report address. | `string` | `null` |

## Outputs

| Name | Description |
|---|---|
| `identity_arn` | SES domain identity ARN. |
| `configuration_set`, `configuration_set_arn` | Configuration set attached to the identity. |
| `send_resource_arns` | Identity and configuration set ARNs, for the worker's `ses:SendEmail` permission (`service` module `mail_send_resource_arns`). |
| `from_address` | `MAIL_FROM`, e.g. `GPUWatch <alerts@example.com>`. |
| `dns_records` | DKIM and MAIL FROM records to publish when the zone is not in Route53. |

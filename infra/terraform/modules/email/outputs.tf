output "identity_arn" {
  description = "ARN of the SES domain identity."
  value       = aws_sesv2_email_identity.domain.arn
}

output "configuration_set_arn" {
  description = "ARN of the configuration set attached to the identity."
  value       = aws_sesv2_configuration_set.this.arn
}

output "configuration_set" {
  description = "Name of the configuration set attached to the identity."
  value       = aws_sesv2_configuration_set.this.configuration_set_name
}

output "send_resource_arns" {
  description = "Resources ses:SendEmail is authorized against for this identity (the identity and its default configuration set), for the worker task role."
  value       = [aws_sesv2_email_identity.domain.arn, aws_sesv2_configuration_set.this.arn]
}

output "from_address" {
  description = "MAIL_FROM for the worker, e.g. \"GPUWatch <alerts@example.com>\"."
  value       = "${var.from_name} <${var.from_local_part}@${var.domain}>"
}

output "dns_records" {
  description = "Records to publish when the zone is not in Route53 (DKIM CNAMEs, MAIL FROM MX and SPF)."
  value = concat(
    [for t in aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens : { type = "CNAME", name = "${t}._domainkey.${var.domain}", value = "${t}.dkim.amazonses.com" }],
    [
      { type = "MX", name = local.mail_from_domain, value = "10 feedback-smtp.${data.aws_region.current.region}.amazonses.com" },
      { type = "TXT", name = local.mail_from_domain, value = "v=spf1 include:amazonses.com ~all" },
    ],
  )
}

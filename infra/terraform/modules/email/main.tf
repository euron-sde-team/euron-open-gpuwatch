# The SES sending identity for alert email. The worker delivers every email notification
# (alert fired, resolved, channel test) through SESv2 SendEmail with MAIL_MODE=ses and
# MAIL_FROM set to `from_address`; the worker task role may send only as this identity.
#
#   - a domain identity with Easy DKIM, attached to a configuration set that requires TLS
#     to the receiving server and suppresses addresses that bounced or complained
#   - a custom MAIL FROM subdomain so SPF aligns with the sending domain
#   - with manage_dns, the DKIM, MAIL FROM and (optionally) DMARC records in Route53;
#     otherwise the `dns_records` output lists what to publish
#
# A new SES account is in the sandbox: it can only send to verified addresses until you
# request production access (docs/guides/deploy-aws.md).
locals {
  mail_from_domain = "${var.mail_from_subdomain}.${var.domain}"
}

resource "aws_sesv2_configuration_set" "this" {
  configuration_set_name = "${var.name_prefix}-alerts"

  delivery_options {
    tls_policy = "REQUIRE"
  }
  reputation_options {
    reputation_metrics_enabled = true
  }
  sending_options {
    sending_enabled = true
  }
  suppression_options {
    suppressed_reasons = ["BOUNCE", "COMPLAINT"]
  }
}

resource "aws_sesv2_email_identity" "domain" {
  email_identity         = var.domain
  configuration_set_name = aws_sesv2_configuration_set.this.configuration_set_name
}

resource "aws_sesv2_email_identity_mail_from_attributes" "domain" {
  email_identity         = aws_sesv2_email_identity.domain.email_identity
  mail_from_domain       = local.mail_from_domain
  behavior_on_mx_failure = "USE_DEFAULT_VALUE"
}

data "aws_region" "current" {}

# ─── DNS (only when the zone is managed in Route53) ─────────────────────────

resource "aws_route53_record" "dkim" {
  count   = var.manage_dns ? 3 : 0
  zone_id = var.route53_zone_id
  name    = "${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.domain}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

resource "aws_route53_record" "mail_from_mx" {
  count   = var.manage_dns ? 1 : 0
  zone_id = var.route53_zone_id
  name    = local.mail_from_domain
  type    = "MX"
  ttl     = 600
  records = ["10 feedback-smtp.${data.aws_region.current.region}.amazonses.com"]
}

resource "aws_route53_record" "mail_from_spf" {
  count   = var.manage_dns ? 1 : 0
  zone_id = var.route53_zone_id
  name    = local.mail_from_domain
  type    = "TXT"
  ttl     = 600
  records = ["v=spf1 include:amazonses.com ~all"]
}

resource "aws_route53_record" "dmarc" {
  count   = var.manage_dns && var.dmarc_policy != null ? 1 : 0
  zone_id = var.route53_zone_id
  name    = "_dmarc.${var.domain}"
  type    = "TXT"
  ttl     = 600
  records = ["v=DMARC1; p=${var.dmarc_policy}; rua=mailto:${var.dmarc_report_address != null ? var.dmarc_report_address : "dmarc-reports@${var.domain}"}"]
}

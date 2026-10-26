# One private bucket for cost and usage report exports: the API writes each generated CSV
# under reports/<report id>.csv and serves it back as a download; rows keep only the
# object key. The worker deletes a report and its object after REPORT_RETENTION_DAYS (30
# by default); the lifecycle rule below is the backstop for an object whose row is gone.
# Reports can be regenerated from the rollups at any time, so the bucket is not versioned.
resource "aws_s3_bucket" "reports" {
  #checkov:skip=CKV_AWS_144:Cross-region replication is pointless for report exports that can be regenerated from the database.
  #checkov:skip=CKV_AWS_18:Access logging targets a separate log bucket an operator chooses; CloudTrail data events cover object access (docs/guides/operations.md).
  #checkov:skip=CKV2_AWS_62:No consumer for S3 event notifications.
  #checkov:skip=CKV_AWS_21:Reports expire after expiration_days and can be regenerated; versioning would only keep expired copies.
  bucket        = "${var.name_prefix}-reports"
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_public_access_block" "reports" {
  bucket                  = aws_s3_bucket.reports.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.kms_key_arn != null ? "aws:kms" : "AES256"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = var.kms_key_arn != null
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  # Reports carry cost and usage per team, workload and host: keep them no longer than
  # the app does (REPORT_RETENTION_DAYS); the worker normally removes row and object first.
  rule {
    id     = "expire-reports"
    status = "Enabled"
    filter {
      prefix = "reports/"
    }
    expiration {
      days = var.expiration_days
    }
  }
}

# Only needed when a browser fetches objects with JavaScript; the dashboard downloads
# reports through the API, so the default is no CORS at all.
resource "aws_s3_bucket_cors_configuration" "reports" {
  count  = length(var.cors_origins) > 0 ? 1 : 0
  bucket = aws_s3_bucket.reports.id
  cors_rule {
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = var.cors_origins
    allowed_headers = ["*"]
    expose_headers  = ["Content-Disposition", "Content-Length", "ETag"]
    max_age_seconds = 3600
  }
}

data "aws_iam_policy_document" "reports" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.reports.arn, "${aws_s3_bucket.reports.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "reports" {
  count      = var.enforce_tls ? 1 : 0
  bucket     = aws_s3_bucket.reports.id
  policy     = data.aws_iam_policy_document.reports.json
  depends_on = [aws_s3_bucket_public_access_block.reports]
}

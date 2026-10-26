output "bucket_name" {
  description = "Reports bucket name (REPORTS_BUCKET)."
  value       = aws_s3_bucket.reports.bucket
}

output "bucket_arn" {
  description = "Reports bucket ARN, for IAM policies."
  value       = aws_s3_bucket.reports.arn
}

output "primary_endpoint_address" {
  description = "Primary endpoint hostname."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "replication_group_id" {
  description = "Replication group id (CloudWatch dimension prefix)."
  value       = aws_elasticache_replication_group.this.id
}

output "member_clusters" {
  description = "Node ids (CloudWatch CacheClusterId dimension)."
  value       = sort(tolist(aws_elasticache_replication_group.this.member_clusters))
}

output "security_group_id" {
  description = "Cache security group; consumers add ingress rules against it."
  value       = aws_security_group.cache.id
}

output "auth_secret_arn" {
  description = "Secrets Manager secret holding AUTH_TOKEN and REDIS_URL."
  value       = aws_secretsmanager_secret.auth.arn
}

output "connection_url" {
  description = "REDIS_URL for the API (rediss://, TLS + AUTH). Pass it to the secrets module, never to plain task environment."
  value       = local.redis_url
  sensitive   = true
}

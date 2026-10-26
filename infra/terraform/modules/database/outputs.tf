output "address" {
  description = "DB hostname."
  value       = aws_db_instance.this.address
}

output "port" {
  description = "DB port."
  value       = aws_db_instance.this.port
}

output "database_name" {
  description = "Database name."
  value       = aws_db_instance.this.db_name
}

output "instance_identifier" {
  description = "RDS instance identifier (CloudWatch dimension)."
  value       = aws_db_instance.this.identifier
}

output "security_group_id" {
  description = "DB security group; consumers add ingress rules against it."
  value       = aws_security_group.db.id
}

output "master_username" {
  description = "Master username."
  value       = aws_db_instance.this.username
}

output "connection_url" {
  description = "DATABASE_URL for the API (SQLAlchemy asyncpg dialect, TLS required). Pass it to the secrets module, never to plain task environment."
  value       = "postgresql+asyncpg://${aws_db_instance.this.username}:${random_password.master.result}@${aws_db_instance.this.address}:${aws_db_instance.this.port}/${aws_db_instance.this.db_name}?ssl=require"
  sensitive   = true
}

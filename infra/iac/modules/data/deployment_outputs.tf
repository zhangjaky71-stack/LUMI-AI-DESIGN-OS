output "postgres_instance_id" {
  value = aws_db_instance.postgres.identifier
}

output "postgres_backup_retention_days" {
  value = aws_db_instance.postgres.backup_retention_period
}

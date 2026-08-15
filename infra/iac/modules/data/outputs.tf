output "postgres_endpoint" {
  value = aws_db_instance.postgres.address
}

output "postgres_port" {
  value = aws_db_instance.postgres.port
}

output "postgres_master_secret_arn" {
  value     = try(aws_db_instance.postgres.master_user_secret[0].secret_arn, null)
  sensitive = true
}

output "redis_primary_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "rabbitmq_instances" {
  value     = aws_mq_broker.rabbitmq.instances
  sensitive = true
}

output "postgres_security_group_id" {
  value = aws_security_group.postgres.id
}

output "redis_security_group_id" {
  value = aws_security_group.redis.id
}

output "rabbitmq_security_group_id" {
  value = aws_security_group.rabbitmq.id
}

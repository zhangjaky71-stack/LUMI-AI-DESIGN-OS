output "migration_task_definition_arn" {
  value = aws_ecs_task_definition.migration.arn
}

output "migration_network" {
  value = {
    cluster_arn        = aws_ecs_cluster.this.arn
    private_subnet_ids = var.private_subnet_ids
    security_group_id  = var.app_security_group_id
  }
}

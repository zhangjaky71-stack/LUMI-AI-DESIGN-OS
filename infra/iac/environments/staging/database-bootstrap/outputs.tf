output "database_bootstrap_task_definition_arn" {
  value = aws_ecs_task_definition.database_bootstrap.arn
}

output "database_bootstrap_network" {
  value = {
    cluster_arn        = aws_ecs_cluster.database_bootstrap.arn
    private_subnet_ids = local.core.private_subnet_ids
    security_group_ids = [
      local.core.app_security_group_id,
      aws_security_group.database_bootstrap_egress.id,
    ]
  }
}

output "database_bootstrap_log_group_name" {
  value = aws_cloudwatch_log_group.database_bootstrap.name
}

output "database_role_secret_arns" {
  value = {
    app       = local.core.secret_arns["database/app"]
    migration = local.core.secret_arns["database/migration"]
  }
}

output "database_bootstrap_api_image" {
  value = var.api_image
}

output "database_bootstrap_release_git_sha" {
  value = var.release_git_sha
}

output "migration_task_definition_arn" { value = module.migration.task_definition_arn }
output "migration_network" {
  value = {
    cluster_arn        = module.migration.cluster_arn
    private_subnet_ids = module.migration.private_subnet_ids
    security_group_id  = module.migration.security_group_id
  }
}

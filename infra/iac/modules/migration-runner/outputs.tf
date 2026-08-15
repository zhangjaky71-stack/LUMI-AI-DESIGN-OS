output "task_definition_arn" { value = aws_ecs_task_definition.this.arn }
output "cluster_arn" { value = aws_ecs_cluster.this.arn }
output "private_subnet_ids" { value = var.private_subnet_ids }
output "security_group_id" { value = var.security_group_id }

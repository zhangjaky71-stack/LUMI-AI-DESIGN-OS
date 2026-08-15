output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "service_names" {
  value = { for name, service in aws_ecs_service.service : name => service.name }
}

output "task_role_arns" {
  value = { for name, role in aws_iam_role.task : name => role.arn }
}

output "execution_role_arns" {
  value = { for name, role in aws_iam_role.execution : name => role.arn }
}

output "alb_arn" {
  value = aws_lb.this.arn
}

output "alb_dns_name" {
  value = aws_lb.this.dns_name
}

output "alb_zone_id" {
  value = aws_lb.this.zone_id
}

output "service_discovery_namespace" {
  value = aws_service_discovery_private_dns_namespace.this.name
}

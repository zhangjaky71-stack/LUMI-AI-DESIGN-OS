output "cluster_arn" { value = module.compute.cluster_arn }
output "service_names" { value = module.compute.service_names }
output "service_desired_counts" { value = module.compute.service_desired_counts }
output "task_role_arns" { value = module.compute.task_role_arns }
output "alb_arn" { value = module.compute.alb_arn }
output "alb_dns_name" { value = module.compute.alb_dns_name }
output "waf_web_acl_arn" { value = module.edge.waf_web_acl_arn }
output "application_fqdn" { value = module.edge.application_fqdn }

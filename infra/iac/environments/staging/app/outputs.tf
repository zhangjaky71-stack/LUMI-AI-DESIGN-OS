output "cluster_arn" { value = module.platform_app.cluster_arn }
output "service_names" { value = module.platform_app.service_names }
output "task_role_arns" { value = module.platform_app.task_role_arns }
output "alb_arn" { value = module.platform_app.alb_arn }
output "alb_dns_name" { value = module.platform_app.alb_dns_name }
output "waf_web_acl_arn" { value = module.platform_app.waf_web_acl_arn }
output "application_fqdn" { value = module.platform_app.application_fqdn }

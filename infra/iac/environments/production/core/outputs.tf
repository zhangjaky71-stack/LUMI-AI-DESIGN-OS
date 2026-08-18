output "vpc_id" { value = module.platform_core.vpc_id }
output "public_subnet_ids" { value = module.platform_core.public_subnet_ids }
output "private_subnet_ids" { value = module.platform_core.private_subnet_ids }
output "data_subnet_ids" { value = module.platform_core.data_subnet_ids }
output "alb_security_group_id" { value = module.platform_core.alb_security_group_id }
output "app_security_group_id" { value = module.platform_core.app_security_group_id }
output "app_internet_egress_security_group_id" { value = module.platform_core.app_internet_egress_security_group_id }
output "sandbox_egress_security_group_id" { value = module.platform_core.sandbox_egress_security_group_id }
output "kms_key_arn" { value = module.platform_core.kms_key_arn }
output "bucket_arns" { value = module.platform_core.bucket_arns }
output "bucket_names" { value = module.platform_core.bucket_names }
output "secret_arns" { value = module.platform_core.secret_arns }
output "postgres_endpoint" { value = module.platform_core.postgres_endpoint }
output "postgres_port" { value = module.platform_core.postgres_port }
output "postgres_master_secret_arn" { value = module.platform_core.postgres_master_secret_arn, sensitive = true }
output "redis_primary_endpoint" { value = module.platform_core.redis_primary_endpoint }
output "rabbitmq_instances" { value = module.platform_core.rabbitmq_instances, sensitive = true }
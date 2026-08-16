output "vpc_id" { value = module.network.vpc_id }
output "public_subnet_ids" { value = module.network.public_subnet_ids }
output "private_subnet_ids" { value = module.network.private_subnet_ids }
output "data_subnet_ids" { value = module.network.data_subnet_ids }
output "alb_security_group_id" { value = module.network.alb_security_group_id }
output "app_security_group_id" { value = module.network.app_security_group_id }
output "sandbox_security_group_id" { value = module.network.sandbox_security_group_id }
output "kms_key_arn" { value = module.storage.kms_key_arn }
output "bucket_arns" { value = module.storage.bucket_arns }
output "bucket_names" { value = module.storage.bucket_names }
output "secret_arns" { value = module.secrets.secret_arns }
output "postgres_endpoint" { value = module.data.postgres_endpoint }
output "postgres_port" { value = module.data.postgres_port }
output "postgres_master_secret_arn" { value = module.data.postgres_master_secret_arn, sensitive = true }
output "redis_primary_endpoint" { value = module.data.redis_primary_endpoint }
output "rabbitmq_instances" { value = module.data.rabbitmq_instances, sensitive = true }

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
output "object_dr_region" { value = var.object_dr_region }
output "object_dr_bucket_names" { value = { for purpose, bucket in aws_s3_bucket.object_dr : purpose => bucket.id } }
output "object_dr_bucket_arns" { value = { for purpose, bucket in aws_s3_bucket.object_dr : purpose => bucket.arn } }
output "object_dr_replication_rule_ids" { value = { for purpose in local.object_dr_purposes : purpose => "lumi-${purpose}-cross-region-dr" } }
output "secret_arns" { value = module.platform_core.secret_arns }
output "postgres_endpoint" { value = module.platform_core.postgres_endpoint }
output "postgres_port" { value = module.platform_core.postgres_port }
output "postgres_instance_id" { value = module.platform_core.postgres_instance_id }
output "postgres_backup_retention_days" { value = module.platform_core.postgres_backup_retention_days }
output "postgres_db_subnet_group_name" { value = module.platform_core.postgres_db_subnet_group_name }
output "postgres_security_group_id" { value = module.platform_core.postgres_security_group_id }
output "postgres_master_secret_arn" { value = module.platform_core.postgres_master_secret_arn, sensitive = true }
output "redis_primary_endpoint" { value = module.platform_core.redis_primary_endpoint }
output "rabbitmq_instances" { value = module.platform_core.rabbitmq_instances, sensitive = true }

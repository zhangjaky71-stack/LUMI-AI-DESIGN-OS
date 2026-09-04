output "region" { value = var.region }
output "availability_zones" { value = var.availability_zones }
output "vpc_id" { value = alicloud_vpc.this.id }
output "public_vswitch_ids" { value = { for zone, item in alicloud_vswitch.public : zone => item.id } }
output "app_vswitch_ids" { value = { for zone, item in alicloud_vswitch.app : zone => item.id } }
output "data_vswitch_ids" { value = { for zone, item in alicloud_vswitch.data : zone => item.id } }
output "app_security_group_id" { value = alicloud_security_group.app.id }
output "sandbox_security_group_id" { value = alicloud_security_group.sandbox.id }
output "ack_cluster_id" { value = var.enable_ack ? alicloud_cs_managed_kubernetes.runtime[0].id : null }
output "ack_cluster_name" { value = var.enable_ack ? alicloud_cs_managed_kubernetes.runtime[0].name : null }
output "bucket_names" { value = { for purpose, bucket in alicloud_oss_bucket.app : purpose => bucket.bucket } }
output "rds_connection_string" { value = alicloud_db_instance.postgres.connection_string }
output "rds_port" { value = alicloud_db_instance.postgres.port }
output "rds_database_name" { value = alicloud_db_database.lumi.data_base_name }
output "rds_account_names" {
  value = {
    app       = alicloud_db_account.app.account_name
    migration = alicloud_db_account.migration.account_name
  }
}
output "redis_connection_domain" { value = alicloud_kvstore_instance.redis.connection_domain }
output "redis_port" { value = alicloud_kvstore_instance.redis.port }
output "acr_namespace" { value = alicloud_cr_namespace.runtime.name }
output "acr_repositories" { value = { for name, repo in alicloud_cr_repo.runtime : name => repo.id } }
output "sls_project" { value = alicloud_log_project.runtime.project_name }
output "amqp_instance_id" { value = var.enable_amqp ? alicloud_amqp_instance.broker[0].id : null }

output "account_id" {
  description = "Authenticated Alibaba Cloud account id."
  value       = local.account_id
}

output "region" {
  description = "Validated Alibaba Cloud deployment region."
  value       = var.region
}

output "availability_zones" {
  description = "Three zones preflighted for VSwitch, RDS PostgreSQL and Redis availability."
  value       = local.zone_ids
}

output "state_bucket" {
  description = "Private, versioned OSS bucket for Terraform state."
  value       = alicloud_oss_bucket.terraform_state.bucket
}

output "state_lock_instance" {
  description = "TableStore instance used by the OSS backend for state locking."
  value       = alicloud_ots_instance.terraform_lock.name
}

output "state_lock_table" {
  description = "TableStore table used by the OSS backend for state locking."
  value       = alicloud_ots_table.terraform_lock.table_name
}

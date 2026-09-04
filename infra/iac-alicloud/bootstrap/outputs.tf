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

output "github_oidc_provider_arn" {
  description = "Non-secret OIDC provider ARN configured in the GitHub Actions workflow."
  value       = alicloud_ims_oidc_provider.github_actions.arn
}

output "github_acr_role_arn" {
  description = "Non-secret RAM role ARN assumed by GitHub Actions."
  value       = alicloud_ram_role.github_acr_push.arn
}

output "github_oidc_subject" {
  description = "Exact GitHub OIDC subject allowed by the role trust policy."
  value       = local.github_oidc_subject
}

output "github_acr_policy_name" {
  description = "Least-privilege custom RAM policy attached to the GitHub Actions role."
  value       = alicloud_ram_policy.github_acr_push.policy_name
}

output "github_acr_repository_boundary" {
  description = "Only ACR repositories under this ARN boundary can be pulled or pushed by the role."
  value       = local.acr_repository_arn
}

data "alicloud_account" "current" {}

data "alicloud_zones" "available" {
  available_resource_creation = "VSwitch"
}

locals {
  account_id         = data.alicloud_account.current.id
  zone_ids           = var.availability_zones
  state_bucket_name  = "lumi-terraform-state-${local.account_id}-${var.region}"
  lock_instance_name = "lumi-tf-${substr(local.account_id, length(local.account_id) - 4, 4)}"
}

resource "alicloud_oss_bucket" "terraform_state" {
  bucket          = local.state_bucket_name
  storage_class   = "Standard"
  redundancy_type = "LRS"
  force_destroy   = false

  tags = {
    Project     = "lumi-ai-design-os"
    Environment = "bootstrap"
    DataClass   = "terraform-state"
  }

  # These settings are owned by dedicated resources below. The provider also
  # reads them back through this legacy inline schema, which otherwise creates
  # a destructive-looking perpetual diff on the bucket resource.
  lifecycle {
    ignore_changes = [versioning, server_side_encryption_rule]
  }
}

resource "alicloud_oss_bucket_acl" "terraform_state" {
  bucket = alicloud_oss_bucket.terraform_state.id
  acl    = "private"
}

resource "alicloud_oss_bucket_public_access_block" "terraform_state" {
  bucket              = alicloud_oss_bucket.terraform_state.id
  block_public_access = true
}

resource "alicloud_oss_bucket_versioning" "terraform_state" {
  bucket = alicloud_oss_bucket.terraform_state.id
  status = "Enabled"
}

resource "alicloud_oss_bucket_server_side_encryption" "terraform_state" {
  bucket        = alicloud_oss_bucket.terraform_state.id
  sse_algorithm = "AES256"
}

resource "alicloud_ots_instance" "terraform_lock" {
  name          = local.lock_instance_name
  instance_type = "Capacity"
  description   = "LUMI Terraform state lock table"

  tags = {
    Project     = "lumi-ai-design-os"
    Environment = "bootstrap"
    DataClass   = "terraform-lock"
  }
}

resource "alicloud_ots_table" "terraform_lock" {
  instance_name = alicloud_ots_instance.terraform_lock.name
  table_name    = "terraform_lock"
  time_to_live  = -1
  max_version   = 1

  primary_key {
    name = "LockID"
    type = "String"
  }
}

check "three_availability_zones" {
  assert {
    condition     = alltrue([for zone in local.zone_ids : contains(data.alicloud_zones.available.ids, zone)])
    error_message = "Every selected availability zone must support VSwitch creation in the deployment region."
  }
}

resource "alicloud_oss_bucket" "app" {
  for_each = local.bucket_names

  bucket          = each.value
  storage_class   = "Standard"
  redundancy_type = "LRS"
  force_destroy   = false
  tags            = merge(local.tags, { Purpose = each.key })

  # Dedicated resources own these protections. Ignore the legacy inline
  # mirror populated by the provider during refresh.
  lifecycle {
    ignore_changes = [versioning, server_side_encryption_rule]
  }
}

resource "alicloud_oss_bucket_acl" "app" {
  for_each = alicloud_oss_bucket.app

  bucket = each.value.id
  acl    = "private"
}

resource "alicloud_oss_bucket_public_access_block" "app" {
  for_each = alicloud_oss_bucket.app

  bucket              = each.value.id
  block_public_access = true
}

resource "alicloud_oss_bucket_versioning" "app" {
  for_each = alicloud_oss_bucket.app

  bucket = each.value.id
  status = "Enabled"
}

resource "alicloud_oss_bucket_server_side_encryption" "app" {
  for_each = alicloud_oss_bucket.app

  bucket        = each.value.id
  sse_algorithm = "AES256"
}

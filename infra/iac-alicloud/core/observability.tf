resource "alicloud_log_project" "runtime" {
  project_name = "${local.name}-${var.account_id}-${var.region}"
  description  = "LUMI staging runtime logs"
  tags         = local.tags
}

resource "alicloud_log_store" "runtime" {
  for_each = local.runtime_names

  project_name          = alicloud_log_project.runtime.project_name
  logstore_name         = each.key
  retention_period      = 14
  shard_count           = 2
  auto_split            = true
  max_split_shard_count = 8
  append_meta           = true
}

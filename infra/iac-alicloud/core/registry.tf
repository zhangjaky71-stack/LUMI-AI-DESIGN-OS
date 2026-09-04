resource "alicloud_cr_namespace" "runtime" {
  name               = "lumistaging${substr(var.account_id, length(var.account_id) - 4, 4)}"
  auto_create        = false
  default_visibility = "PRIVATE"
}

resource "alicloud_cr_repo" "runtime" {
  for_each = local.runtime_names

  namespace = alicloud_cr_namespace.runtime.name
  name      = each.key
  summary   = "LUMI ${each.key} immutable runtime images"
  repo_type = "PRIVATE"
  detail    = "Images are promoted by immutable digest from the protected release workflow."
}

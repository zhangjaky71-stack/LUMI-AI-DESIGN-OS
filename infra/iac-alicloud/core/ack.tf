resource "alicloud_cs_managed_kubernetes" "runtime" {
  count = var.enable_ack ? 1 : 0

  name                         = "${local.name}-ack"
  cluster_spec                 = "ack.pro.small"
  vswitch_ids                  = [for zone in var.availability_zones : alicloud_vswitch.app[zone].id]
  pod_vswitch_ids              = [for zone in var.availability_zones : alicloud_vswitch.app[zone].id]
  service_cidr                 = "172.21.0.0/20"
  new_nat_gateway              = false
  slb_internet_enabled         = false
  enable_rrsa                  = true
  is_enterprise_security_group = true
  deletion_protection          = false
  timezone                     = "Asia/Shanghai"
  tags                         = merge(local.tags, { Runtime = "ack-auto-mode" })

  auto_mode {
    enabled = true
  }

  addons {
    name = "terway-eniip"
  }

  addons {
    name = "alb-ingress-controller"
  }

  addons {
    name = "managed-aliyun-acr-credential-helper"
  }

  addons {
    name = "loongcollector"
  }

  addons {
    name = "metrics-server"
  }

  addons {
    name = "managed-coredns"
  }

  addons {
    name = "arms-prometheus"
  }

  audit_log_config {
    enabled          = true
    sls_project_name = alicloud_log_project.runtime.project_name
  }

  depends_on = [
    alicloud_snat_entry.app,
    alicloud_log_store.runtime,
  ]
}

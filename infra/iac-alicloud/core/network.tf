resource "alicloud_vpc" "this" {
  vpc_name    = "${local.name}-vpc"
  cidr_block  = "10.42.0.0/16"
  description = "LUMI staging VPC"
  tags        = local.tags
}

resource "alicloud_vswitch" "public" {
  for_each = local.zones

  vpc_id       = alicloud_vpc.this.id
  zone_id      = each.key
  cidr_block   = local.public_cidrs[each.value]
  vswitch_name = "${local.name}-public-${each.key}"
  description  = "Public edge tier for ${each.key}"
  tags         = merge(local.tags, { Tier = "public" })
}

resource "alicloud_vswitch" "app" {
  for_each = local.zones

  vpc_id       = alicloud_vpc.this.id
  zone_id      = each.key
  cidr_block   = local.app_cidrs[each.value]
  vswitch_name = "${local.name}-app-${each.key}"
  description  = "Private application tier for ${each.key}"
  tags         = merge(local.tags, { Tier = "app" })
}

resource "alicloud_vswitch" "data" {
  for_each = local.zones

  vpc_id       = alicloud_vpc.this.id
  zone_id      = each.key
  cidr_block   = local.data_cidrs[each.value]
  vswitch_name = "${local.name}-data-${each.key}"
  description  = "Private data tier for ${each.key}"
  tags         = merge(local.tags, { Tier = "data" })
}

resource "alicloud_eip_address" "nat" {
  for_each = var.enable_nat_gateways ? local.zones : {}

  address_name         = "${local.name}-nat-${each.key}"
  payment_type         = "PayAsYouGo"
  internet_charge_type = "PayByTraffic"
  bandwidth            = "5"
  tags                 = merge(local.tags, { Purpose = "nat-egress" })
}

resource "alicloud_nat_gateway" "this" {
  for_each = var.enable_nat_gateways ? local.zones : {}

  vpc_id           = alicloud_vpc.this.id
  vswitch_id       = alicloud_vswitch.public[each.key].id
  nat_gateway_name = "${local.name}-nat-${each.key}"
  nat_type         = "Enhanced"
  payment_type     = "PayAsYouGo"
  network_type     = "internet"
  tags             = merge(local.tags, { Purpose = "app-egress" })
}

resource "alicloud_eip_association" "nat" {
  for_each = var.enable_nat_gateways ? local.zones : {}

  allocation_id = alicloud_eip_address.nat[each.key].id
  instance_id   = alicloud_nat_gateway.this[each.key].id
  instance_type = "Nat"
}

resource "alicloud_snat_entry" "app" {
  for_each = var.enable_nat_gateways ? local.zones : {}

  snat_table_id     = alicloud_nat_gateway.this[each.key].snat_table_ids
  source_vswitch_id = alicloud_vswitch.app[each.key].id
  snat_ip           = alicloud_eip_address.nat[each.key].ip_address
  snat_entry_name   = "${local.name}-app-${each.key}"

  depends_on = [alicloud_eip_association.nat]
}

resource "alicloud_security_group" "app" {
  security_group_name = "${local.name}-app"
  description         = "Private LUMI application runtimes"
  vpc_id              = alicloud_vpc.this.id
  inner_access_policy = "Accept"
  tags                = local.tags
}

resource "alicloud_security_group_rule" "app_https_egress" {
  type              = "egress"
  ip_protocol       = "tcp"
  port_range        = "443/443"
  cidr_ip           = "0.0.0.0/0"
  policy            = "accept"
  priority          = 10
  security_group_id = alicloud_security_group.app.id
  description       = "Provider, package and webhook TLS egress"
}

resource "alicloud_security_group_rule" "app_vpc_egress" {
  type              = "egress"
  ip_protocol       = "all"
  port_range        = "-1/-1"
  cidr_ip           = alicloud_vpc.this.cidr_block
  policy            = "accept"
  priority          = 20
  security_group_id = alicloud_security_group.app.id
  description       = "Private service and data traffic"
}

resource "alicloud_security_group" "sandbox" {
  security_group_name = "${local.name}-sandbox"
  description         = "Sandbox runtime with VPC-only baseline egress"
  vpc_id              = alicloud_vpc.this.id
  inner_access_policy = "Drop"
  tags                = merge(local.tags, { SecurityBoundary = "sandbox" })
}

resource "alicloud_security_group_rule" "sandbox_vpc_egress" {
  type              = "egress"
  ip_protocol       = "all"
  port_range        = "-1/-1"
  cidr_ip           = alicloud_vpc.this.cidr_block
  policy            = "accept"
  priority          = 10
  security_group_id = alicloud_security_group.sandbox.id
  description       = "Fail-closed private VPC egress baseline"
}

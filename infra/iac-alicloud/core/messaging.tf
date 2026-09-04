locals {
  job_queues = {
    "lumi.media.image"      = "image.transform"
    "lumi.media.video"      = "video.render"
    "lumi.media.export"     = "export.package"
    "lumi.asset.processing" = "asset.processing"
  }

  dead_letter_queues = {
    for name, _ in local.job_queues : "${name}.dlq" => "${name}.dead"
  }
}

resource "alicloud_amqp_instance" "broker" {
  count = var.enable_amqp ? 1 : 0

  instance_name     = "${local.name}-rabbitmq"
  payment_type      = var.amqp_payment_type
  serverless_switch = true
  support_eip       = false
  vpc_id            = alicloud_vpc.this.id
  vswitch_ids       = [for zone in var.availability_zones : alicloud_vswitch.data[zone].id]
  security_group_id = alicloud_security_group.app.id
  tags              = merge(local.tags, { DataClass = "job-events" })
}

resource "alicloud_amqp_virtual_host" "lumi" {
  count = var.enable_amqp ? 1 : 0

  instance_id       = alicloud_amqp_instance.broker[0].id
  virtual_host_name = "lumi"
}

resource "alicloud_amqp_exchange" "exchange" {
  for_each = var.enable_amqp ? {
    "lumi.jobs"   = "DIRECT"
    "lumi.domain" = "TOPIC"
    "lumi.dlx"    = "TOPIC"
  } : {}

  instance_id       = alicloud_amqp_instance.broker[0].id
  virtual_host_name = alicloud_amqp_virtual_host.lumi[0].virtual_host_name
  exchange_name     = each.key
  exchange_type     = each.value
  internal          = false
  auto_delete_state = false
}

resource "alicloud_amqp_queue" "job" {
  for_each = var.enable_amqp ? local.job_queues : {}

  instance_id             = alicloud_amqp_instance.broker[0].id
  virtual_host_name       = alicloud_amqp_virtual_host.lumi[0].virtual_host_name
  queue_name              = each.key
  auto_delete_state       = false
  dead_letter_exchange    = alicloud_amqp_exchange.exchange["lumi.dlx"].exchange_name
  dead_letter_routing_key = "${each.key}.dead"
}

resource "alicloud_amqp_queue" "dead_letter" {
  for_each = var.enable_amqp ? local.dead_letter_queues : {}

  instance_id       = alicloud_amqp_instance.broker[0].id
  virtual_host_name = alicloud_amqp_virtual_host.lumi[0].virtual_host_name
  queue_name        = each.key
  auto_delete_state = false
}

resource "alicloud_amqp_binding" "job" {
  for_each = var.enable_amqp ? local.job_queues : {}

  instance_id       = alicloud_amqp_instance.broker[0].id
  virtual_host_name = alicloud_amqp_virtual_host.lumi[0].virtual_host_name
  source_exchange   = alicloud_amqp_exchange.exchange["lumi.jobs"].exchange_name
  destination_name  = alicloud_amqp_queue.job[each.key].queue_name
  binding_type      = "QUEUE"
  binding_key       = each.value
}

resource "alicloud_amqp_binding" "dead_letter" {
  for_each = var.enable_amqp ? local.dead_letter_queues : {}

  instance_id       = alicloud_amqp_instance.broker[0].id
  virtual_host_name = alicloud_amqp_virtual_host.lumi[0].virtual_host_name
  source_exchange   = alicloud_amqp_exchange.exchange["lumi.dlx"].exchange_name
  destination_name  = alicloud_amqp_queue.dead_letter[each.key].queue_name
  binding_type      = "QUEUE"
  binding_key       = each.value
}

resource "random_password" "db_account" {
  length      = 32
  special     = false
  min_upper   = 6
  min_lower   = 6
  min_numeric = 6
}

resource "random_password" "db_migration" {
  length      = 32
  special     = false
  min_upper   = 6
  min_lower   = 6
  min_numeric = 6
}

resource "random_password" "redis" {
  length      = 32
  special     = false
  min_upper   = 6
  min_lower   = 6
  min_numeric = 6
}

resource "alicloud_db_instance" "postgres" {
  instance_name            = "${local.name}-postgres"
  engine                   = "PostgreSQL"
  engine_version           = "15.0"
  instance_type            = "pg.n1e.1c.1m"
  instance_storage         = 20
  db_instance_storage_type = "cloud_essd"
  category                 = "Basic"
  instance_charge_type     = "Postpaid"
  zone_id                  = var.availability_zones[0]
  vswitch_id               = alicloud_vswitch.data[var.availability_zones[0]].id
  vpc_id                   = alicloud_vpc.this.id
  security_group_ids       = [alicloud_security_group.app.id]
  security_ips             = local.app_cidrs
  deletion_protection      = false
  maintain_time            = "18:00Z-19:00Z"
  tags                     = merge(local.tags, { DataClass = "application" })
}

resource "alicloud_db_database" "lumi" {
  instance_id    = alicloud_db_instance.postgres.id
  data_base_name = "lumi"
  character_set  = "UTF8"
  description    = "LUMI staging application database"
}

resource "alicloud_db_account" "app" {
  db_instance_id      = alicloud_db_instance.postgres.id
  account_name        = "lumi_app"
  account_password    = random_password.db_account.result
  account_type        = "Normal"
  account_description = "LUMI staging application account"
}

resource "alicloud_db_account" "migration" {
  db_instance_id      = alicloud_db_instance.postgres.id
  account_name        = "lumi_migration"
  account_password    = random_password.db_migration.result
  account_type        = "Normal"
  account_description = "LUMI staging schema migration account"
}

resource "alicloud_db_account_privilege" "app" {
  instance_id  = alicloud_db_instance.postgres.id
  account_name = alicloud_db_account.app.account_name
  db_names     = [alicloud_db_database.lumi.data_base_name]
  privilege    = "ReadWrite"
}

resource "alicloud_db_account_privilege" "migration" {
  instance_id  = alicloud_db_instance.postgres.id
  account_name = alicloud_db_account.migration.account_name
  db_names     = [alicloud_db_database.lumi.data_base_name]
  privilege    = "DBOwner"
}

resource "alicloud_kvstore_instance" "redis" {
  db_instance_name    = "${local.name}-redis"
  instance_type       = "Redis"
  engine_version      = "5.0"
  instance_class      = "redis.amber.master.small.multithread"
  payment_type        = "PostPaid"
  zone_id             = var.availability_zones[1]
  secondary_zone_id   = var.availability_zones[2]
  vswitch_id          = alicloud_vswitch.data[var.availability_zones[1]].id
  password            = random_password.redis.result
  security_group_id   = alicloud_security_group.app.id
  security_ips        = local.app_cidrs
  ssl_enable          = "Enable"
  maintain_start_time = "19:00Z"
  maintain_end_time   = "20:00Z"
  tags                = merge(local.tags, { DataClass = "cache-session" })
}

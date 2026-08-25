locals {
  project           = "lumi"
  environment       = "staging"
  rabbitmq_username = "lumi_app"
  tags = {
    Owner       = "platform"
    DataClass   = "synthetic-only"
    ReleaseNode = "NODE-72"
  }
  secret_names = toset([
    "database/app",
    "database/migration",
    "redis/url",
    "rabbitmq/url",
    "providers/model",
    "providers/media",
    "providers/search",
    "billing/webhook",
    "auth/signing",
    "internal/model-gateway",
    "internal/tool-gateway",
    "internal/sandbox-runtime",
    "internal/side-effect-control",
    "internal/tool-audit",
    "internal/tool-approval",
    "internal/tool-data",
    "internal/agent-control",
  ])
  generated_internal_secret_names = toset([
    "auth/signing",
    "internal/model-gateway",
    "internal/tool-gateway",
    "internal/sandbox-runtime",
    "internal/side-effect-control",
    "internal/tool-audit",
    "internal/tool-approval",
    "internal/tool-data",
    "internal/agent-control",
  ])
}

resource "random_password" "redis_auth_token" {
  length      = 64
  special     = false
  min_upper   = 8
  min_lower   = 8
  min_numeric = 8
}

resource "random_password" "rabbitmq_password" {
  length      = 48
  special     = false
  min_upper   = 8
  min_lower   = 8
  min_numeric = 8
}

ephemeral "random_password" "internal_secret" {
  for_each = local.generated_internal_secret_names

  length      = 64
  special     = false
  min_upper   = 8
  min_lower   = 8
  min_numeric = 8
}

module "platform_core" {
  source = "../../../modules/platform-core"

  project                 = local.project
  environment             = local.environment
  account_id              = var.account_id
  region                  = var.region
  vpc_cidr                = "10.40.0.0/16"
  availability_zones      = var.availability_zones
  public_subnet_cidrs     = ["10.40.0.0/24", "10.40.1.0/24", "10.40.2.0/24"]
  private_subnet_cidrs    = ["10.40.16.0/20", "10.40.32.0/20", "10.40.48.0/20"]
  data_subnet_cidrs       = ["10.40.80.0/24", "10.40.81.0/24", "10.40.82.0/24"]
  postgres_engine_version = var.postgres_engine_version
  db_instance_class       = var.db_instance_class
  db_multi_az             = true
  redis_engine_version    = var.redis_engine_version
  redis_node_type         = var.redis_node_type
  redis_auth_token        = random_password.redis_auth_token.result
  rabbitmq_engine_version = var.rabbitmq_engine_version
  rabbitmq_instance_type  = var.rabbitmq_instance_type
  rabbitmq_username       = local.rabbitmq_username
  rabbitmq_password       = random_password.rabbitmq_password.result
  secret_names            = local.secret_names
  tags                    = local.tags
}

resource "aws_secretsmanager_secret_version" "redis_url" {
  secret_id = module.platform_core.secret_arns["redis/url"]
  secret_string_wo = format(
    "rediss://:%s@%s:6379/0",
    random_password.redis_auth_token.result,
    module.platform_core.redis_primary_endpoint,
  )
  secret_string_wo_version = 1
}

resource "aws_secretsmanager_secret_version" "rabbitmq_url" {
  secret_id = module.platform_core.secret_arns["rabbitmq/url"]
  secret_string_wo = replace(
    module.platform_core.rabbitmq_instances[0].endpoints[0],
    "amqps://",
    "amqps://${local.rabbitmq_username}:${random_password.rabbitmq_password.result}@",
  )
  secret_string_wo_version = 1
}

resource "aws_secretsmanager_secret_version" "internal_secret" {
  for_each = local.generated_internal_secret_names

  secret_id                = module.platform_core.secret_arns[each.key]
  secret_string_wo         = ephemeral.random_password.internal_secret[each.key].result
  secret_string_wo_version = 1
}

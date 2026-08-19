locals {
  project     = "lumi"
  environment = "production"
  tags = {
    Owner       = "platform"
    DataClass   = "customer-production"
    ReleaseNode = "NODE-72"
  }
  secret_names = toset([
    "database/app",
    "database/migration",
    "redis/url",
    "rabbitmq/url",
    "providers/model",
    "providers/media",
    "billing/webhook",
    "auth/signing",
    "internal/model-gateway",
    "internal/tool-gateway",
    "internal/sandbox-runtime",
  ])
}

module "platform_core" {
  source = "../../../modules/platform-core"

  project                 = local.project
  environment             = local.environment
  account_id              = var.account_id
  region                  = var.region
  vpc_cidr                = "10.80.0.0/16"
  availability_zones      = var.availability_zones
  public_subnet_cidrs     = ["10.80.0.0/24", "10.80.1.0/24", "10.80.2.0/24"]
  private_subnet_cidrs    = ["10.80.16.0/20", "10.80.32.0/20", "10.80.48.0/20"]
  data_subnet_cidrs       = ["10.80.80.0/24", "10.80.81.0/24", "10.80.82.0/24"]
  postgres_engine_version = var.postgres_engine_version
  db_instance_class       = var.db_instance_class
  db_multi_az              = true
  redis_engine_version     = var.redis_engine_version
  redis_node_type          = var.redis_node_type
  redis_auth_token         = var.redis_auth_token
  rabbitmq_engine_version  = var.rabbitmq_engine_version
  rabbitmq_instance_type   = var.rabbitmq_instance_type
  rabbitmq_username        = var.rabbitmq_username
  rabbitmq_password        = var.rabbitmq_password
  secret_names             = local.secret_names
  tags                     = local.tags
}

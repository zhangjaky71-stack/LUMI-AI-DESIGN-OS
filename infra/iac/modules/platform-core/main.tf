module "network" {
  source = "../network"

  project                = var.project
  environment            = var.environment
  vpc_cidr               = var.vpc_cidr
  availability_zones     = var.availability_zones
  public_subnet_cidrs    = var.public_subnet_cidrs
  private_subnet_cidrs   = var.private_subnet_cidrs
  data_subnet_cidrs      = var.data_subnet_cidrs
  tags                    = var.tags
}

module "storage" {
  source = "../storage"

  project     = var.project
  environment = var.environment
  account_id  = var.account_id
  region      = var.region
  tags        = var.tags
}

module "data" {
  source = "../data"

  project                   = var.project
  environment               = var.environment
  vpc_id                    = module.network.vpc_id
  data_subnet_ids           = module.network.data_subnet_ids
  app_security_group_id     = module.network.app_security_group_id
  sandbox_security_group_id = module.network.sandbox_security_group_id
  kms_key_arn               = module.storage.kms_key_arn
  postgres_engine_version   = var.postgres_engine_version
  db_instance_class         = var.db_instance_class
  db_multi_az               = var.db_multi_az
  redis_engine_version      = var.redis_engine_version
  redis_node_type           = var.redis_node_type
  redis_auth_token          = var.redis_auth_token
  rabbitmq_engine_version   = var.rabbitmq_engine_version
  rabbitmq_instance_type    = var.rabbitmq_instance_type
  rabbitmq_username         = var.rabbitmq_username
  rabbitmq_password         = var.rabbitmq_password
  tags                      = var.tags
}

module "secrets" {
  source = "../secrets"

  project      = var.project
  environment  = var.environment
  kms_key_arn  = module.storage.kms_key_arn
  secret_names = var.secret_names
  tags         = var.tags
}

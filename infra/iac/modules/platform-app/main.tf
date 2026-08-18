module "compute" {
  source = "../compute"

  project                               = var.project
  environment                           = var.environment
  vpc_id                                = var.vpc_id
  public_subnet_ids                      = var.public_subnet_ids
  private_subnet_ids                     = var.private_subnet_ids
  app_security_group_id                  = var.app_security_group_id
  app_internet_egress_security_group_id = var.app_internet_egress_security_group_id
  sandbox_egress_security_group_id       = var.sandbox_egress_security_group_id
  alb_security_group_id                  = var.alb_security_group_id
  certificate_arn                        = var.certificate_arn
  kms_key_arn                            = var.kms_key_arn
  services                               = var.services
  tags                                   = var.tags
}

module "edge" {
  source = "../edge"

  project                    = var.project
  environment                = var.environment
  domain_name                = var.domain_name
  hosted_zone_id             = var.hosted_zone_id
  alb_arn                    = module.compute.alb_arn
  alb_dns_name               = module.compute.alb_dns_name
  alb_zone_id                = module.compute.alb_zone_id
  rate_limit_requests_per_5m = var.waf_rate_limit_requests_per_5m
  tags                       = var.tags
}
data "terraform_remote_state" "core" {
  backend = "s3"
  config = { bucket = var.core_state_bucket, key = var.core_state_key, region = var.region }
}

locals { core = data.terraform_remote_state.core.outputs }

module "migration" {
  source = "../../../modules/migration-runner"

  project              = "lumi"
  environment          = "production"
  private_subnet_ids   = local.core.private_subnet_ids
  security_group_id    = local.core.app_security_group_id
  kms_key_arn          = local.core.kms_key_arn
  image                = var.api_image
  migration_secret_arn = local.core.secret_arns["database/migration"]
  tags = { Owner = "platform", ReleaseNode = "NODE-72" }
}

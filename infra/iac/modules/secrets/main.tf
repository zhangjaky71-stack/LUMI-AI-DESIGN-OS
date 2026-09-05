locals {
  name = "${var.project}-${var.environment}"
  tags = merge(var.tags, {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_secretsmanager_secret" "this" {
  for_each = var.secret_names

  name                    = "${local.name}/${each.value}"
  description             = "LUMI ${var.environment} secret container: ${each.value}. Value is provisioned outside Terraform."
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.environment == "production" ? 30 : 7

  tags = merge(local.tags, { SecretPurpose = each.value })
}

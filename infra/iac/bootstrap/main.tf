resource "aws_kms_key" "terraform_state" {
  description             = "LUMI Terraform state encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "terraform_state" {
  name          = "alias/lumi-terraform-state"
  target_key_id = aws_kms_key.terraform_state.key_id
}

resource "aws_s3_bucket" "terraform_state" {
  bucket = var.state_bucket_name
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.terraform_state.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

data "aws_iam_policy_document" "terraform_state" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.terraform_state.arn,
      "${aws_s3_bucket.terraform_state.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  policy = data.aws_iam_policy_document.terraform_state.json
}

data "aws_caller_identity" "current" {}

locals {
  deployment_roles = {
    staging = {
      subject = "repo:${var.github_repository}:environment:staging"
    }
    production = {
      subject = "repo:${var.github_repository}:environment:production"
    }
  }
}

data "aws_iam_policy_document" "github_assume" {
  for_each = local.deployment_roles

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.github_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [each.value.subject]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  for_each = local.deployment_roles

  name                 = "lumi-${each.key}-github-deploy"
  assume_role_policy   = data.aws_iam_policy_document.github_assume[each.key].json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "github_state" {
  statement {
    sid       = "StateBucketMetadata"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = [aws_s3_bucket.terraform_state.arn]
  }
  statement {
    sid = "StateObjectAndLockAccess"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.terraform_state.arn}/*"]
  }
  statement {
    sid = "StateKmsAccess"
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]
    resources = [aws_kms_key.terraform_state.arn]
  }
}

resource "aws_iam_role_policy" "github_state" {
  for_each = aws_iam_role.github_deploy
  name     = "terraform-state"
  role     = each.value.id
  policy   = data.aws_iam_policy_document.github_state.json
}

# This is a bootstrap provisioning role, not an application runtime role. It is
# restricted by GitHub Environment OIDC subject and only includes AWS services
# managed by NODE-72. Runtime ECS task roles remain service-specific/minimal.
data "aws_iam_policy_document" "github_platform_provisioner" {
  statement {
    sid = "ProvisionLumiPlatform"
    actions = [
      "ec2:*",
      "ecs:*",
      "elasticloadbalancing:*",
      "application-autoscaling:*",
      "rds:*",
      "elasticache:*",
      "mq:*",
      "s3:*",
      "kms:*",
      "secretsmanager:*",
      "logs:*",
      "cloudwatch:*",
      "servicediscovery:*",
      "route53:*",
      "wafv2:*",
      "iam:*",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_platform_provisioner" {
  for_each = aws_iam_role.github_deploy
  name     = "lumi-platform-provisioner"
  role     = each.value.id
  policy   = data.aws_iam_policy_document.github_platform_provisioner.json
}

output "state_bucket" {
  value = aws_s3_bucket.terraform_state.bucket
}

output "state_kms_key_arn" {
  value = aws_kms_key.terraform_state.arn
}

output "github_deploy_role_arns" {
  value = { for environment, role in aws_iam_role.github_deploy : environment => role.arn }
}

locals {
  object_dr_sources = {
    assets  = module.platform_core.bucket_names["assets"]
    exports = module.platform_core.bucket_names["exports"]
  }

  object_dr_bucket_names = {
    for purpose, _ in local.object_dr_sources :
    purpose => "${local.project}-${local.environment}-${var.account_id}-${var.object_dr_region}-${purpose}-dr"
  }
}

resource "aws_kms_key" "object_dr" {
  provider                = aws.object_dr
  description             = "LUMI Production cross-region object recovery replicas"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  tags = merge(local.tags, {
    Name          = "${local.project}-${local.environment}-object-dr"
    RecoveryClass = "cross-region-object-dr"
  })
}

resource "aws_kms_alias" "object_dr" {
  provider      = aws.object_dr
  name          = "alias/${local.project}-${local.environment}-object-dr"
  target_key_id = aws_kms_key.object_dr.key_id
}

resource "aws_s3_bucket" "object_dr" {
  provider = aws.object_dr
  for_each = local.object_dr_sources

  bucket = local.object_dr_bucket_names[each.key]

  tags = merge(local.tags, {
    Name          = local.object_dr_bucket_names[each.key]
    Purpose       = each.key
    RecoveryClass = "cross-region-object-dr"
    SourceRegion  = var.region
  })
}

resource "aws_s3_bucket_ownership_controls" "object_dr" {
  provider = aws.object_dr
  for_each = aws_s3_bucket.object_dr

  bucket = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "object_dr" {
  provider = aws.object_dr
  for_each = aws_s3_bucket.object_dr

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "object_dr" {
  provider = aws.object_dr
  for_each = aws_s3_bucket.object_dr

  bucket = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "object_dr" {
  provider = aws.object_dr
  for_each = aws_s3_bucket.object_dr

  bucket = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.object_dr.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

data "aws_iam_policy_document" "object_dr_tls_only" {
  for_each = aws_s3_bucket.object_dr

  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      each.value.arn,
      "${each.value.arn}/*",
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

resource "aws_s3_bucket_policy" "object_dr_tls_only" {
  provider = aws.object_dr
  for_each = aws_s3_bucket.object_dr

  bucket = each.value.id
  policy = data.aws_iam_policy_document.object_dr_tls_only[each.key].json

  depends_on = [aws_s3_bucket_public_access_block.object_dr]
}

data "aws_iam_policy_document" "object_dr_replication_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "object_dr_replication" {
  name               = "${local.project}-${local.environment}-object-dr-replication"
  assume_role_policy = data.aws_iam_policy_document.object_dr_replication_assume.json

  tags = merge(local.tags, {
    RecoveryClass = "cross-region-object-dr"
  })
}

data "aws_iam_policy_document" "object_dr_replication" {
  statement {
    sid    = "ReadReplicationConfiguration"
    effect = "Allow"
    actions = [
      "s3:GetReplicationConfiguration",
      "s3:ListBucket",
    ]
    resources = [for _, name in local.object_dr_sources : "arn:aws:s3:::${name}"]
  }

  statement {
    sid    = "ReadSourceVersions"
    effect = "Allow"
    actions = [
      "s3:GetObjectVersionForReplication",
      "s3:GetObjectVersionAcl",
      "s3:GetObjectVersionTagging",
      "s3:GetObjectRetention",
      "s3:GetObjectLegalHold",
    ]
    resources = [for _, name in local.object_dr_sources : "arn:aws:s3:::${name}/*"]
  }

  statement {
    sid    = "DecryptSourceObjects"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = [module.platform_core.kms_key_arn]
  }

  statement {
    sid    = "WriteReplicaVersions"
    effect = "Allow"
    actions = [
      "s3:ReplicateObject",
      "s3:ReplicateDelete",
      "s3:ReplicateTags",
    ]
    resources = [for _, bucket in aws_s3_bucket.object_dr : "${bucket.arn}/*"]
  }

  statement {
    sid    = "EncryptReplicaObjects"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]
    resources = [aws_kms_key.object_dr.arn]
  }
}

resource "aws_iam_role_policy" "object_dr_replication" {
  name   = "${local.project}-${local.environment}-object-dr-replication"
  role   = aws_iam_role.object_dr_replication.id
  policy = data.aws_iam_policy_document.object_dr_replication.json
}

resource "aws_s3_bucket_replication_configuration" "object_dr" {
  for_each = local.object_dr_sources

  bucket = each.value
  role   = aws_iam_role.object_dr_replication.arn

  rule {
    id       = "critical-${each.key}-cross-region"
    priority = 1
    status   = "Enabled"

    filter {}

    delete_marker_replication {
      status = "Enabled"
    }

    source_selection_criteria {
      sse_kms_encrypted_objects {
        status = "Enabled"
      }
    }

    destination {
      bucket        = aws_s3_bucket.object_dr[each.key].arn
      storage_class = "STANDARD"

      encryption_configuration {
        replica_kms_key_id = aws_kms_key.object_dr.arn
      }

      metrics {
        status = "Enabled"
        event_threshold {
          minutes = 15
        }
      }

      replication_time {
        status = "Enabled"
        time {
          minutes = 15
        }
      }
    }
  }

  depends_on = [
    module.platform_core,
    aws_iam_role_policy.object_dr_replication,
    aws_s3_bucket_versioning.object_dr,
    aws_s3_bucket_server_side_encryption_configuration.object_dr,
  ]
}

output "object_dr_region" {
  value = var.object_dr_region
}

output "object_dr_bucket_names" {
  value = { for purpose, bucket in aws_s3_bucket.object_dr : purpose => bucket.bucket }
}

output "object_dr_bucket_arns" {
  value = { for purpose, bucket in aws_s3_bucket.object_dr : purpose => bucket.arn }
}

output "object_dr_kms_key_arn" {
  value = aws_kms_key.object_dr.arn
}

output "object_dr_replication_role_arn" {
  value = aws_iam_role.object_dr_replication.arn
}

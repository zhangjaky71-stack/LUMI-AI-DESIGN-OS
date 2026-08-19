locals {
  critical_object_dr_buckets = {
    assets  = module.platform_core.bucket_names["assets"]
    exports = module.platform_core.bucket_names["exports"]
  }
  critical_object_dr_bucket_arns = {
    assets  = module.platform_core.bucket_arns["assets"]
    exports = module.platform_core.bucket_arns["exports"]
  }
  object_dr_bucket_names = {
    for name, _ in local.critical_object_dr_buckets :
    name => "${local.project}-${local.environment}-${var.account_id}-${var.object_dr_region}-${name}-dr"
  }
}

resource "aws_kms_key" "object_dr" {
  provider                = aws.dr
  description             = "${local.project}-${local.environment} cross-region object recovery encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  tags                    = merge(local.tags, { Name = "${local.project}-${local.environment}-object-dr-kms", Purpose = "cross-region-object-recovery" })
}

resource "aws_kms_alias" "object_dr" {
  provider      = aws.dr
  name          = "alias/${local.project}-${local.environment}-object-dr"
  target_key_id = aws_kms_key.object_dr.key_id
}

resource "aws_s3_bucket" "object_dr" {
  provider = aws.dr
  for_each = local.object_dr_bucket_names

  bucket        = each.value
  force_destroy = false
  tags = merge(local.tags, {
    Name          = each.value
    Purpose       = "cross-region-object-recovery"
    SourcePurpose = each.key
  })
}

resource "aws_s3_bucket_ownership_controls" "object_dr" {
  provider = aws.dr
  for_each = aws_s3_bucket.object_dr

  bucket = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "object_dr" {
  provider = aws.dr
  for_each = aws_s3_bucket.object_dr

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "object_dr" {
  provider = aws.dr
  for_each = aws_s3_bucket.object_dr

  bucket = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "object_dr" {
  provider = aws.dr
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

resource "aws_s3_bucket_lifecycle_configuration" "object_dr" {
  provider = aws.dr
  for_each = aws_s3_bucket.object_dr

  bucket = each.value.id

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  dynamic "rule" {
    for_each = each.key == "exports" ? [1] : []
    content {
      id     = "expire-replicated-exports"
      status = "Enabled"
      filter {}
      expiration {
        days = 7
      }
      noncurrent_version_expiration {
        noncurrent_days = 7
      }
    }
  }
}

data "aws_iam_policy_document" "object_dr_tls_only" {
  provider = aws.dr
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
  provider = aws.dr
  for_each = aws_s3_bucket.object_dr

  bucket = each.value.id
  policy = data.aws_iam_policy_document.object_dr_tls_only[each.key].json

  depends_on = [aws_s3_bucket_public_access_block.object_dr]
}

data "aws_iam_policy_document" "object_dr_assume" {
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
  assume_role_policy = data.aws_iam_policy_document.object_dr_assume.json
  tags               = merge(local.tags, { Purpose = "cross-region-object-recovery" })
}

data "aws_iam_policy_document" "object_dr_replication" {
  statement {
    sid     = "ReadSourceReplicationConfiguration"
    effect  = "Allow"
    actions = ["s3:GetReplicationConfiguration", "s3:ListBucket"]
    resources = [
      for _, arn in local.critical_object_dr_bucket_arns : arn
    ]
  }

  statement {
    sid    = "ReadSourceVersions"
    effect = "Allow"
    actions = [
      "s3:GetObjectVersionForReplication",
      "s3:GetObjectVersionAcl",
      "s3:GetObjectVersionTagging",
    ]
    resources = [
      for _, arn in local.critical_object_dr_bucket_arns : "${arn}/*"
    ]
  }

  statement {
    sid     = "DecryptSourceObjects"
    effect  = "Allow"
    actions = ["kms:Decrypt", "kms:DescribeKey"]
    resources = [
      module.platform_core.kms_key_arn,
    ]
  }

  statement {
    sid    = "ReplicateToRecoveryBuckets"
    effect = "Allow"
    actions = [
      "s3:ReplicateObject",
      "s3:ReplicateDelete",
      "s3:ReplicateTags",
    ]
    resources = [
      for _, bucket in aws_s3_bucket.object_dr : "${bucket.arn}/*"
    ]
  }

  statement {
    sid    = "EncryptRecoveryReplicas"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]
    resources = [
      aws_kms_key.object_dr.arn,
    ]
  }
}

resource "aws_iam_role_policy" "object_dr_replication" {
  name   = "cross-region-object-recovery"
  role   = aws_iam_role.object_dr_replication.id
  policy = data.aws_iam_policy_document.object_dr_replication.json
}

resource "aws_s3_bucket_replication_configuration" "object_dr" {
  for_each = local.critical_object_dr_buckets

  role   = aws_iam_role.object_dr_replication.arn
  bucket = each.value

  rule {
    id       = "cross-region-recovery-${each.key}"
    priority = each.key == "assets" ? 10 : 20
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
    aws_s3_bucket_versioning.object_dr,
    aws_iam_role_policy.object_dr_replication,
  ]
}

locals {
  object_dr_purposes = toset(["assets", "exports"])
  object_dr_source_bucket_names = {
    for purpose in local.object_dr_purposes : purpose => module.platform_core.bucket_names[purpose]
  }
  object_dr_source_bucket_arns = {
    for purpose in local.object_dr_purposes : purpose => module.platform_core.bucket_arns[purpose]
  }
  object_dr_bucket_names = {
    for purpose in local.object_dr_purposes : purpose =>
    "${local.project}-${local.environment}-${var.account_id}-${var.object_dr_region}-${purpose}-dr"
  }
}

resource "aws_kms_key" "object_dr" {
  provider = aws.object_dr

  description             = "LUMI production cross-region object disaster-recovery encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  tags = merge(local.tags, {
    Name    = "lumi-production-object-dr"
    Purpose = "cross-region-object-recovery"
  })
}

resource "aws_kms_alias" "object_dr" {
  provider = aws.object_dr

  name          = "alias/lumi-production-object-dr"
  target_key_id = aws_kms_key.object_dr.key_id
}

resource "aws_s3_bucket" "object_dr" {
  provider = aws.object_dr
  for_each = local.object_dr_bucket_names

  bucket = each.value
  tags = merge(local.tags, {
    Name            = each.value
    Purpose         = "${each.key}-cross-region-dr"
    SourceRegion    = var.region
    RecoveryRegion  = var.object_dr_region
    RecoveryClass   = "critical"
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

data "aws_iam_policy_document" "object_replication_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "object_replication" {
  name               = "lumi-production-object-dr-replication"
  assume_role_policy = data.aws_iam_policy_document.object_replication_assume.json
  tags                = local.tags
}

data "aws_iam_policy_document" "object_replication" {
  statement {
    sid = "ReadSourceReplicationConfiguration"
    actions = [
      "s3:GetReplicationConfiguration",
      "s3:ListBucket",
    ]
    resources = values(local.object_dr_source_bucket_arns)
  }

  statement {
    sid = "ReadSourceVersions"
    actions = [
      "s3:GetObjectVersionForReplication",
      "s3:GetObjectVersionAcl",
      "s3:GetObjectVersionTagging",
    ]
    resources = [for arn in values(local.object_dr_source_bucket_arns) : "${arn}/*"]
  }

  statement {
    sid = "ReplicateDestinationObjects"
    actions = [
      "s3:ReplicateObject",
      "s3:ReplicateTags",
    ]
    resources = [for bucket in values(aws_s3_bucket.object_dr) : "${bucket.arn}/*"]
  }

  statement {
    sid       = "DecryptSourceObjects"
    actions   = ["kms:Decrypt"]
    resources = [module.platform_core.kms_key_arn]
  }

  statement {
    sid = "EncryptDestinationReplicas"
    actions = [
      "kms:Encrypt",
      "kms:GenerateDataKey",
    ]
    resources = [aws_kms_key.object_dr.arn]
  }
}

resource "aws_iam_role_policy" "object_replication" {
  name   = "cross-region-object-dr"
  role   = aws_iam_role.object_replication.id
  policy = data.aws_iam_policy_document.object_replication.json
}

resource "aws_s3_bucket_replication_configuration" "object_dr" {
  for_each = local.object_dr_source_bucket_names

  role   = aws_iam_role.object_replication.arn
  bucket = each.value

  rule {
    id       = "lumi-${each.key}-cross-region-dr"
    priority = 1
    status   = "Enabled"

    filter {}

    # A source-side delete must not erase the independently recoverable copy.
    delete_marker_replication {
      status = "Disabled"
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
    aws_s3_bucket_versioning.object_dr,
    aws_iam_role_policy.object_replication,
  ]
}

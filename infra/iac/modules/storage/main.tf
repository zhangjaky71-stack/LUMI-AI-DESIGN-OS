locals {
  name = "${var.project}-${var.environment}"
  tags = merge(var.tags, {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  })
  buckets = {
    assets  = "${local.name}-${var.account_id}-${var.region}-assets"
    exports = "${local.name}-${var.account_id}-${var.region}-exports"
    sandbox = "${local.name}-${var.account_id}-${var.region}-sandbox"
  }
}

resource "aws_kms_key" "this" {
  description             = "${local.name} application data encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  tags                    = merge(local.tags, { Name = "${local.name}-data-kms" })
}

resource "aws_kms_alias" "this" {
  name          = "alias/${local.name}-data"
  target_key_id = aws_kms_key.this.key_id
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets
  bucket   = each.value
  tags     = merge(local.tags, { Name = each.value, Purpose = each.key })
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.this.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id

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
      id     = "expire-exports"
      status = "Enabled"
      filter {}
      expiration {
        days = var.export_expiration_days
      }
      noncurrent_version_expiration {
        noncurrent_days = var.export_expiration_days
      }
    }
  }

  dynamic "rule" {
    for_each = each.key == "sandbox" ? [1] : []
    content {
      id     = "expire-sandbox"
      status = "Enabled"
      filter {}
      expiration {
        days = var.sandbox_expiration_days
      }
      noncurrent_version_expiration {
        noncurrent_days = var.sandbox_expiration_days
      }
    }
  }
}

data "aws_iam_policy_document" "tls_only" {
  for_each = aws_s3_bucket.this
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

resource "aws_s3_bucket_policy" "tls_only" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  policy   = data.aws_iam_policy_document.tls_only[each.key].json

  depends_on = [aws_s3_bucket_public_access_block.this]
}

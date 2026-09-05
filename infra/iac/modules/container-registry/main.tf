locals {
  repositories = {
    for name in var.runtime_names :
    name => "${var.project}-${var.environment}-${name}"
  }

  tags = merge(var.tags, {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_ecr_repository" "runtime" {
  for_each = local.repositories

  name                 = each.value
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(local.tags, {
    Name    = each.value
    Runtime = each.key
    Purpose = "runtime-release-promotion"
  })
}

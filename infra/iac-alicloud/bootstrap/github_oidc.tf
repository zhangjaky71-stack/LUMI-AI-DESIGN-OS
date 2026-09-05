locals {
  github_oidc_subject = "repo:${var.github_repository}:ref:${var.github_ref}"
  acr_repository_arn  = "acs:cr:${var.region}:${local.account_id}:repository/${var.acr_namespace}/*"
}

resource "alicloud_ims_oidc_provider" "github_actions" {
  oidc_provider_name = var.github_oidc_provider_name
  issuer_url         = "https://token.actions.githubusercontent.com"
  client_ids         = ["sts.aliyuncs.com"]
  # SHA-1 thumbprint of the self-signed ISRG Root X1 CA serving GitHub's
  # OIDC endpoint. Verified from the live certificate chain on 2026-09-04.
  fingerprints = ["CABD2A79A1076A31F21D253635CB039D4329A5E8"]
  description  = "GitHub Actions OIDC provider for LUMI deployments"
}

resource "alicloud_ram_role" "github_acr_push" {
  role_name            = var.github_acr_role_name
  description          = "Short-lived GitHub Actions role for pushing LUMI staging images to ACR"
  max_session_duration = 3600

  assume_role_policy_document = jsonencode({
    Version = "1"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Principal = {
          Federated = [alicloud_ims_oidc_provider.github_actions.arn]
        }
        Condition = {
          StringEquals = {
            "oidc:iss" = "https://token.actions.githubusercontent.com"
            "oidc:aud" = "sts.aliyuncs.com"
            "oidc:sub" = local.github_oidc_subject
          }
        }
      }
    ]
  })

  tags = {
    Project     = "lumi-ai-design-os"
    Environment = "staging"
    ManagedBy   = "terraform"
  }
}

resource "alicloud_ram_policy" "github_acr_push" {
  policy_name     = var.github_acr_policy_name
  description     = "Allow the LUMI GitHub Actions role to obtain a temporary ACR token and push staging images"
  rotate_strategy = "DeleteOldestNonDefaultVersionWhenLimitExceeded"

  policy_document = jsonencode({
    Version = "1"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["cr:GetAuthorizationToken"]
        Resource = ["*"]
      },
      {
        Effect = "Allow"
        Action = [
          "cr:PullRepository",
          "cr:PushRepository",
        ]
        Resource = [local.acr_repository_arn]
      }
    ]
  })

  tags = {
    Project     = "lumi-ai-design-os"
    Environment = "staging"
    ManagedBy   = "terraform"
  }
}

resource "alicloud_ram_role_policy_attachment" "github_acr_push" {
  policy_name = alicloud_ram_policy.github_acr_push.policy_name
  policy_type = alicloud_ram_policy.github_acr_push.type
  role_name   = alicloud_ram_role.github_acr_push.role_name
}

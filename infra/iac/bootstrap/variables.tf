variable "region" {
  type        = string
  description = "AWS region for Terraform state resources and release deployment roles."
}

variable "state_bucket_name" {
  type        = string
  default     = null
  nullable    = true
  description = "Optional globally unique S3 bucket name for Terraform state. When omitted, LUMI derives one from account id and region."

  validation {
    condition = (
      var.state_bucket_name == null ||
      can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    )
    error_message = "state_bucket_name must be null or a valid lowercase S3 bucket name."
  }
}

variable "github_oidc_provider_arn" {
  type        = string
  default     = null
  nullable    = true
  description = "Optional existing account-level GitHub Actions OIDC provider ARN. When omitted, bootstrap creates token.actions.githubusercontent.com with sts.amazonaws.com audience."

  validation {
    condition = (
      var.github_oidc_provider_arn == null ||
      can(regex("^arn:aws:iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$", var.github_oidc_provider_arn))
    )
    error_message = "github_oidc_provider_arn must be null or the AWS IAM provider for token.actions.githubusercontent.com."
  }
}

variable "github_repository" {
  type        = string
  default     = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
  description = "Exact GitHub owner/repository trusted by the deployment roles."
}

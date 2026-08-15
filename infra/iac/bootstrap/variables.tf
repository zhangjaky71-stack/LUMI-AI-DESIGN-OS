variable "region" {
  type        = string
  description = "AWS region for Terraform state resources."
}

variable "state_bucket_name" {
  type        = string
  description = "Globally unique S3 bucket name for Terraform state."
}

variable "github_oidc_provider_arn" {
  type        = string
  description = "Existing account-level GitHub Actions OIDC provider ARN for token.actions.githubusercontent.com."
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$", var.github_oidc_provider_arn))
    error_message = "github_oidc_provider_arn must be the AWS IAM provider for token.actions.githubusercontent.com."
  }
}

variable "github_repository" {
  type        = string
  default     = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
  description = "Exact GitHub owner/repository trusted by the deployment roles."
}

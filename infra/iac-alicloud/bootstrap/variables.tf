variable "region" {
  description = "Alibaba Cloud region selected from the authenticated account."
  type        = string
  default     = "cn-hangzhou"

  validation {
    condition     = can(regex("^[a-z0-9]+(?:-[a-z0-9]+)+$", var.region))
    error_message = "region must be a valid Alibaba Cloud region id."
  }
}

variable "profile" {
  description = "Alibaba Cloud CLI OAuth profile used only for local bootstrap."
  type        = string
  default     = "lumi-deploy"
}

variable "availability_zones" {
  description = "Three zones verified to offer the staging RDS and Redis SKUs."
  type        = list(string)
  default     = ["cn-hangzhou-h", "cn-hangzhou-i", "cn-hangzhou-j"]

  validation {
    condition     = length(var.availability_zones) == 3 && length(distinct(var.availability_zones)) == 3
    error_message = "availability_zones must contain exactly three distinct zones."
  }
}

variable "github_repository" {
  description = "GitHub owner/repository allowed to exchange an OIDC token for the ACR push role."
  type        = string
  default     = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use the owner/repository form."
  }
}

variable "github_ref" {
  description = "Exact Git ref allowed to assume the GitHub Actions ACR push role."
  type        = string
  default     = "refs/heads/main"

  validation {
    condition     = startswith(var.github_ref, "refs/heads/")
    error_message = "github_ref must identify an exact branch under refs/heads/."
  }
}

variable "github_oidc_provider_name" {
  description = "Alibaba Cloud OIDC provider name used by GitHub Actions."
  type        = string
  default     = "lumi-github-actions"
}

variable "github_acr_role_name" {
  description = "RAM role assumed by the pinned GitHub Actions workflow."
  type        = string
  default     = "lumi-github-acr-push"
}

variable "github_acr_policy_name" {
  description = "Custom RAM policy granting the GitHub Actions role access to staging ACR repositories."
  type        = string
  default     = "LumiGitHubAcrPush"
}

variable "acr_namespace" {
  description = "Personal ACR namespace that bounds the GitHub Actions push policy."
  type        = string
  default     = "lumistaging3251"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_-]{1,118}[a-z0-9]$", var.acr_namespace))
    error_message = "acr_namespace must be a valid ACR namespace."
  }
}

variable "account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account id."
  }
}

variable "region" { type = string }

variable "core_state_bucket" { type = string }

variable "core_state_key" {
  type    = string
  default = "lumi/staging/core/terraform.tfstate"
}

variable "release_git_sha" {
  type = string
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.release_git_sha))
    error_message = "release_git_sha must be an exact 40-character lowercase Git SHA."
  }
}

variable "api_image" {
  type = string
  validation {
    condition = can(regex(
      "^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/lumi-staging-api@sha256:[0-9a-f]{64}$",
      var.api_image,
    ))
    error_message = "api_image must be the exact immutable Staging ECR API digest."
  }
}

variable "credential_generation" {
  type    = number
  default = 1
  validation {
    condition     = var.credential_generation >= 1 && floor(var.credential_generation) == var.credential_generation
    error_message = "credential_generation must be a positive integer."
  }
}

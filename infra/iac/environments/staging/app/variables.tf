variable "account_id" { type = string }
variable "region" { type = string }
variable "core_state_bucket" { type = string }
variable "core_state_key" { type = string, default = "lumi/staging/core/terraform.tfstate" }
variable "certificate_arn" { type = string }
variable "domain_name" { type = string }
variable "hosted_zone_id" { type = string }

variable "api_image" { type = string }
variable "agent_runtime_image" { type = string }
variable "model_gateway_image" { type = string }
variable "tool_gateway_image" { type = string }
variable "worker_media_image" { type = string }
variable "sandbox_runtime_image" { type = string }

variable "stripe_plan_catalog_json" {
  description = "Server-owned Stripe test plan/version/Price catalog JSON."
  type        = string
  validation {
    condition     = can(jsondecode(var.stripe_plan_catalog_json)) && length(trimspace(var.stripe_plan_catalog_json)) > 2
    error_message = "stripe_plan_catalog_json must be non-empty valid JSON."
  }
}

variable "waf_rate_limit_requests_per_5m" { type = number, default = 1000 }

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

variable "video_model_profile" {
  type        = string
  description = "Logical Model Gateway profile that must match one media-secret video_models[*].profiles entry."
  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$", var.video_model_profile))
    error_message = "video_model_profile must be a valid Model Gateway logical profile."
  }
}

variable "waf_rate_limit_requests_per_5m" { type = number, default = 1000 }

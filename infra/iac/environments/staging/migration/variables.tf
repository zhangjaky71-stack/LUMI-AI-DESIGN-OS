variable "account_id" { type = string }
variable "region" { type = string }
variable "core_state_bucket" { type = string }
variable "core_state_key" { type = string, default = "lumi/staging/core/terraform.tfstate" }
variable "api_image" { type = string }

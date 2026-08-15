variable "project" { type = string }
variable "environment" { type = string }
variable "account_id" { type = string }
variable "region" { type = string }

variable "export_expiration_days" {
  type    = number
  default = 7
  validation {
    condition     = var.export_expiration_days >= 1 && var.export_expiration_days <= 30
    error_message = "Export expiration must be between 1 and 30 days."
  }
}

variable "sandbox_expiration_days" {
  type    = number
  default = 3
  validation {
    condition     = var.sandbox_expiration_days >= 1 && var.sandbox_expiration_days <= 14
    error_message = "Sandbox expiration must be between 1 and 14 days."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

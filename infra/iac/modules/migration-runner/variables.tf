variable "project" { type = string }
variable "environment" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "security_group_id" { type = string }
variable "kms_key_arn" { type = string }
variable "image" {
  type = string
  validation {
    condition     = can(regex("^[^\\s@]+@sha256:[0-9a-f]{64}$", var.image))
    error_message = "Migration image must be an immutable @sha256 digest."
  }
}
variable "migration_secret_arn" { type = string }
variable "command" {
  type    = list(string)
  default = ["alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"]
}
variable "cpu" { type = number, default = 1024 }
variable "memory" { type = number, default = 2048 }
variable "tags" { type = map(string), default = {} }

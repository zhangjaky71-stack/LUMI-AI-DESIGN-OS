variable "project" { type = string }
variable "environment" { type = string }
variable "kms_key_arn" { type = string }

variable "secret_names" {
  type        = set(string)
  description = "Secret containers only. Values are provisioned outside Terraform to avoid persisting credentials in IaC state."
}

variable "tags" {
  type    = map(string)
  default = {}
}

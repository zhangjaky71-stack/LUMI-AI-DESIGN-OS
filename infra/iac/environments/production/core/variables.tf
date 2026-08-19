variable "account_id" { type = string }
variable "region" { type = string }
variable "object_dr_region" {
  type = string
  validation {
    condition     = length(trimspace(var.object_dr_region)) > 0 && var.object_dr_region != var.region
    error_message = "Production object_dr_region must be configured and differ from the primary region."
  }
}
variable "availability_zones" {
  type = list(string)
  validation {
    condition     = length(var.availability_zones) == 3 && length(distinct(var.availability_zones)) == 3
    error_message = "Production must use exactly three distinct availability zones."
  }
}
variable "postgres_engine_version" { type = string }
variable "db_instance_class" { type = string, default = "db.r6g.large" }
variable "redis_engine_version" { type = string }
variable "redis_node_type" { type = string, default = "cache.r6g.large" }
variable "rabbitmq_engine_version" { type = string }
variable "rabbitmq_instance_type" { type = string }
variable "redis_auth_token" { type = string, sensitive = true }
variable "rabbitmq_username" { type = string, sensitive = true }
variable "rabbitmq_password" { type = string, sensitive = true }

variable "account_id" { type = string }
variable "region" { type = string }
variable "availability_zones" {
  type = list(string)
  validation {
    condition     = length(var.availability_zones) == 3 && length(distinct(var.availability_zones)) == 3
    error_message = "Staging must use exactly three distinct availability zones to preserve production topology class."
  }
}
variable "postgres_engine_version" { type = string }
variable "db_instance_class" { type = string, default = "db.t4g.medium" }
variable "redis_engine_version" { type = string }
variable "redis_node_type" { type = string, default = "cache.t4g.small" }
variable "rabbitmq_engine_version" { type = string }
variable "rabbitmq_instance_type" { type = string }
variable "redis_auth_token" { type = string, sensitive = true }
variable "rabbitmq_username" { type = string, sensitive = true }
variable "rabbitmq_password" { type = string, sensitive = true }

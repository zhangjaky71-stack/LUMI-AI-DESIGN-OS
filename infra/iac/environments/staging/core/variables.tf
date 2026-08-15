variable "account_id" { type = string }
variable "region" { type = string }
variable "state_bucket" { type = string }
variable "postgres_engine_version" { type = string }
variable "redis_engine_version" { type = string }
variable "rabbitmq_engine_version" { type = string }
variable "rabbitmq_instance_type" { type = string }
variable "redis_auth_token" { type = string, sensitive = true }
variable "rabbitmq_username" { type = string, sensitive = true }
variable "rabbitmq_password" { type = string, sensitive = true }

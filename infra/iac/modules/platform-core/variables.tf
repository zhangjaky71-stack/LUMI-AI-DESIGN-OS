variable "project" { type = string }
variable "environment" { type = string }
variable "account_id" { type = string }
variable "region" { type = string }
variable "vpc_cidr" { type = string }
variable "availability_zones" { type = list(string) }
variable "public_subnet_cidrs" { type = list(string) }
variable "private_subnet_cidrs" { type = list(string) }
variable "data_subnet_cidrs" { type = list(string) }
variable "postgres_engine_version" { type = string }
variable "db_instance_class" { type = string }
variable "db_multi_az" { type = bool }
variable "redis_engine_version" { type = string }
variable "redis_node_type" { type = string }
variable "redis_auth_token" { type = string, sensitive = true }
variable "rabbitmq_engine_version" { type = string }
variable "rabbitmq_instance_type" { type = string }
variable "rabbitmq_username" { type = string, sensitive = true }
variable "rabbitmq_password" { type = string, sensitive = true }
variable "secret_names" { type = set(string) }
variable "tags" { type = map(string), default = {} }

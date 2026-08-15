variable "project" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "data_subnet_ids" {
  type = list(string)
  validation {
    condition     = length(var.data_subnet_ids) >= 3
    error_message = "CLUSTER_MULTI_AZ RabbitMQ requires at least three data subnets/AZs in this LUMI topology."
  }
}
variable "app_security_group_id" { type = string }
variable "kms_key_arn" { type = string }

variable "postgres_engine_version" {
  type        = string
  description = "Pinned PostgreSQL major/minor supported by the target AWS region."
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 100
}

variable "db_max_allocated_storage_gb" {
  type    = number
  default = 500
}

variable "db_multi_az" {
  type    = bool
  default = true
}

variable "db_backup_retention_days" {
  type    = number
  default = 14
  validation {
    condition     = var.db_backup_retention_days >= 7 && var.db_backup_retention_days <= 35
    error_message = "Production-class backup retention must be 7..35 days."
  }
}

variable "redis_engine_version" {
  type        = string
  description = "Pinned Redis engine version supported by the target AWS region."
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "redis_auth_token" {
  type        = string
  sensitive   = true
  description = "Redis auth token. Store outside source control; Terraform state must be encrypted/restricted."
  validation {
    condition     = length(var.redis_auth_token) >= 16
    error_message = "redis_auth_token must be at least 16 characters."
  }
}

variable "rabbitmq_engine_version" {
  type        = string
  description = "Pinned RabbitMQ engine version supported by Amazon MQ in the target region."
}

variable "rabbitmq_instance_type" {
  type        = string
  description = "Amazon MQ instance type selected after region/cost validation."
}

variable "rabbitmq_username" {
  type      = string
  sensitive = true
}

variable "rabbitmq_password" {
  type        = string
  sensitive   = true
  description = "Amazon MQ bootstrap password. State backend must be encrypted and tightly access-controlled."
  validation {
    condition     = length(var.rabbitmq_password) >= 16
    error_message = "rabbitmq_password must be at least 16 characters."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

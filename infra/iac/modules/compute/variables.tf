variable "project" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "app_security_group_id" { type = string }
variable "alb_security_group_id" { type = string }
variable "certificate_arn" { type = string }
variable "kms_key_arn" { type = string }

variable "services" {
  description = "Production deployment units. Exactly one service must be publicly_routed."
  type = map(object({
    image                    = string
    cpu                      = number
    memory                   = number
    desired_count            = number
    min_capacity             = number
    max_capacity             = number
    container_port           = optional(number, 8080)
    command                  = optional(list(string), [])
    publicly_routed          = optional(bool, false)
    health_check_path        = optional(string, "/health/ready")
    environment              = optional(map(string), {})
    secret_arns              = optional(map(string), {})
    s3_bucket_arns           = optional(list(string), [])
    autoscale_metric_name    = string
    autoscale_target_value   = number
  }))

  validation {
    condition     = length([for _, service in var.services : 1 if service.publicly_routed]) == 1
    error_message = "Exactly one ECS service must be publicly_routed."
  }

  validation {
    condition = alltrue([
      for _, service in var.services :
      can(regex("^[^\\s@]+@sha256:[0-9a-f]{64}$", service.image)) &&
      service.cpu > 0 && service.memory > 0 &&
      service.min_capacity >= 1 &&
      service.max_capacity >= service.min_capacity &&
      service.desired_count >= service.min_capacity &&
      service.desired_count <= service.max_capacity &&
      service.autoscale_target_value > 0
    ])
    error_message = "Service images must be immutable digests and capacity/metric values must be valid."
  }
}

variable "migration_task" {
  description = "One-shot Alembic migration task. It is registered by Terraform but never run automatically by ECS service reconciliation."
  type = object({
    image               = string
    migration_secret_arn = string
    cpu                 = optional(number, 1024)
    memory              = optional(number, 2048)
    command             = optional(list(string), ["alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"])
  })
  validation {
    condition     = can(regex("^[^\\s@]+@sha256:[0-9a-f]{64}$", var.migration_task.image)) && length(var.migration_task.migration_secret_arn) > 10
    error_message = "Migration image must use immutable digest and migration_secret_arn must be set."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

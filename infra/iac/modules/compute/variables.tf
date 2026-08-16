variable "project" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "isolated_subnet_ids" { type = list(string) }
variable "app_security_group_id" { type = string }
variable "sandbox_security_group_id" { type = string }
variable "alb_security_group_id" { type = string }
variable "certificate_arn" { type = string }
variable "kms_key_arn" { type = string }

variable "public_canary_percent" {
  type    = number
  default = 5
  validation {
    condition     = var.public_canary_percent >= 0.1 && var.public_canary_percent <= 25
    error_message = "Public canary percent must be between 0.1 and 25."
  }
}

variable "public_canary_bake_time_minutes" {
  type    = number
  default = 10
  validation {
    condition     = var.public_canary_bake_time_minutes >= 5 && var.public_canary_bake_time_minutes <= 60
    error_message = "Public canary bake time must be between 5 and 60 minutes."
  }
}

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
    isolated_network         = optional(bool, false)
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
      service.autoscale_target_value > 0 &&
      !(service.publicly_routed && service.isolated_network)
    ])
    error_message = "Service images/capacity must be valid and isolated services cannot be public."
  }

  validation {
    condition = !contains(keys(var.services), "sandbox-runtime") || (
      var.services["sandbox-runtime"].isolated_network
    )
    error_message = "sandbox-runtime must use isolated_network=true."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "project" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "app_security_group_id" { type = string }
variable "app_internet_egress_security_group_id" { type = string }
variable "sandbox_egress_security_group_id" { type = string }
variable "alb_security_group_id" { type = string }
variable "certificate_arn" { type = string }
variable "kms_key_arn" { type = string }
variable "domain_name" { type = string }
variable "hosted_zone_id" { type = string }
variable "services" {
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
}
variable "waf_rate_limit_requests_per_5m" { type = number, default = 2000 }
variable "tags" { type = map(string), default = {} }
variable "project" { type = string }
variable "environment" { type = string }
variable "domain_name" { type = string }
variable "hosted_zone_id" { type = string }
variable "alb_arn" { type = string }
variable "alb_dns_name" { type = string }
variable "alb_zone_id" { type = string }

variable "rate_limit_requests_per_5m" {
  type    = number
  default = 2000
  validation {
    condition     = var.rate_limit_requests_per_5m >= 100 && var.rate_limit_requests_per_5m <= 2000000
    error_message = "WAF rate limit must be between 100 and 2,000,000 requests per 5 minutes."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

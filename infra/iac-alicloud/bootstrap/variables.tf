variable "region" {
  description = "Alibaba Cloud region selected from the authenticated account."
  type        = string
  default     = "cn-hangzhou"

  validation {
    condition     = can(regex("^[a-z0-9]+(?:-[a-z0-9]+)+$", var.region))
    error_message = "region must be a valid Alibaba Cloud region id."
  }
}

variable "profile" {
  description = "Alibaba Cloud CLI OAuth profile used only for local bootstrap."
  type        = string
  default     = "lumi-deploy"
}

variable "availability_zones" {
  description = "Three zones verified to offer the staging RDS and Redis SKUs."
  type        = list(string)
  default     = ["cn-hangzhou-h", "cn-hangzhou-i", "cn-hangzhou-j"]

  validation {
    condition     = length(var.availability_zones) == 3 && length(distinct(var.availability_zones)) == 3
    error_message = "availability_zones must contain exactly three distinct zones."
  }
}

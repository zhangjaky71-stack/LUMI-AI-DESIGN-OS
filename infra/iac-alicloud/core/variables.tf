variable "region" {
  description = "Alibaba Cloud deployment region."
  type        = string
  default     = "cn-hangzhou"
}

variable "profile" {
  description = "Alibaba Cloud CLI profile used for local deployment."
  type        = string
  default     = "lumi-deploy"
}

variable "account_id" {
  description = "Alibaba Cloud account id used only in globally unique resource names."
  type        = string
  default     = "1153410507483251"
}

variable "availability_zones" {
  description = "Zones preflighted for VSwitch, RDS PostgreSQL and Redis availability."
  type        = list(string)
  default     = ["cn-hangzhou-h", "cn-hangzhou-i", "cn-hangzhou-j"]

  validation {
    condition     = length(var.availability_zones) == 3 && length(distinct(var.availability_zones)) == 3
    error_message = "availability_zones must contain exactly three distinct zones."
  }
}

variable "enable_nat_gateways" {
  description = "Create one pay-as-you-go NAT gateway and EIP per application zone."
  type        = bool
  default     = true
}

variable "enable_ack" {
  description = "Create the ACK Managed Pro cluster in Auto Mode for the LUMI runtimes."
  type        = bool
  default     = true
}

variable "enable_amqp" {
  description = "Create Alibaba Cloud Message Queue for RabbitMQ after the service and billing terms are activated."
  type        = bool
  default     = false
}

variable "amqp_payment_type" {
  description = "Billing model for the RabbitMQ instance."
  type        = string
  default     = "PayAsYouGo"
}

variable "tags" {
  description = "Additional tags applied to supported resources."
  type        = map(string)
  default     = {}
}

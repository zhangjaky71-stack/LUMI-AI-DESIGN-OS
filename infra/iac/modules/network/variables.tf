variable "project" {
  type        = string
  description = "Project prefix used in resource names."
}

variable "environment" {
  type        = string
  description = "Environment name such as staging or production."
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR."
}

variable "availability_zones" {
  type        = list(string)
  description = "At least two AZs."
  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "At least two availability zones are required."
  }
}

variable "public_subnet_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.public_subnet_cidrs) == length(var.availability_zones)
    error_message = "public_subnet_cidrs must match availability_zones length."
  }
}

variable "private_subnet_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.private_subnet_cidrs) == length(var.availability_zones)
    error_message = "private_subnet_cidrs must match availability_zones length."
  }
}

variable "data_subnet_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.data_subnet_cidrs) == length(var.availability_zones)
    error_message = "data_subnet_cidrs must match availability_zones length."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

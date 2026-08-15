variable "region" {
  type        = string
  description = "AWS region for Terraform state resources."
}

variable "state_bucket_name" {
  type        = string
  description = "Globally unique S3 bucket name for Terraform state."
}

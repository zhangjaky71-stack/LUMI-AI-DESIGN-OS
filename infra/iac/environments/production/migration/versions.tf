terraform {
  required_version = ">= 1.8.0, < 2.0.0"
  backend "s3" {}
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0, < 7.0"
    }
  }
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags {
    tags = { Project = "lumi", Environment = "production", ManagedBy = "terraform" }
  }
}

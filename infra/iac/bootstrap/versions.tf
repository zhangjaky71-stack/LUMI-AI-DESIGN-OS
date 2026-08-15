terraform {
  required_version = ">= 1.14.6, < 1.15.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.55.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "lumi"
      ManagedBy = "terraform"
      Purpose   = "terraform-state-bootstrap"
    }
  }
}

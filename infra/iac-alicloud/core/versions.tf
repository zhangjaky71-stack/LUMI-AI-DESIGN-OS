terraform {
  required_version = ">= 1.14.6, < 1.15.0"

  required_providers {
    alicloud = {
      source  = "aliyun/alicloud"
      version = "1.291.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.9.0"
    }
  }

  backend "oss" {}
}

provider "alicloud" {
  region  = var.region
  profile = var.profile
}

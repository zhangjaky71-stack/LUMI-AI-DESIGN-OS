locals {
  project     = "lumi"
  environment = "staging"
  name        = "${local.project}-${local.environment}"

  zones = {
    for index, zone in var.availability_zones : zone => index
  }

  public_cidrs = ["10.42.0.0/24", "10.42.1.0/24", "10.42.2.0/24"]
  app_cidrs    = ["10.42.16.0/20", "10.42.32.0/20", "10.42.48.0/20"]
  data_cidrs   = ["10.42.80.0/24", "10.42.81.0/24", "10.42.82.0/24"]

  runtime_names = toset([
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
  ])

  bucket_names = {
    assets  = "${local.name}-${var.account_id}-${var.region}-assets"
    exports = "${local.name}-${var.account_id}-${var.region}-exports"
    sandbox = "${local.name}-${var.account_id}-${var.region}-sandbox"
  }

  tags = merge(var.tags, {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "terraform"
    Cloud       = "alicloud"
  })
}

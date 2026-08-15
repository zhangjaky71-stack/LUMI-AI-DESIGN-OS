data "terraform_remote_state" "core" {
  backend = "s3"
  config = {
    bucket = var.core_state_bucket
    key    = var.core_state_key
    region = var.region
  }
}

locals {
  project     = "lumi"
  environment = "production"
  core        = data.terraform_remote_state.core.outputs
  secret_arns = local.core.secret_arns
  bucket_arns = local.core.bucket_arns

  common_environment = {
    LUMI_ENV               = local.environment
    LUMI_REDIS_HOST        = local.core.redis_primary_endpoint
    LUMI_SERVICE_DISCOVERY = "production.lumi.internal"
  }

  services = {
    api = {
      image             = var.api_image
      cpu               = 2048
      memory            = 4096
      desired_count     = 3
      min_capacity      = 3
      max_capacity      = 12
      publicly_routed   = true
      health_check_path = "/health/ready"
      environment = merge(local.common_environment, { LUMI_ROLE = "api" })
      secret_arns = {
        LUMI_DATABASE_URL           = local.secret_arns["database/app"]
        LUMI_REDIS_URL              = local.secret_arns["redis/url"]
        LUMI_RABBITMQ_URL           = local.secret_arns["rabbitmq/url"]
        LUMI_BILLING_WEBHOOK_SECRET = local.secret_arns["billing/webhook"]
        LUMI_AUTH_SIGNING_SECRET    = local.secret_arns["auth/signing"]
      }
      s3_bucket_arns         = [local.bucket_arns["assets"], local.bucket_arns["exports"]]
      autoscale_metric_name  = "ApiConcurrentRequests"
      autoscale_target_value = 100
    }

    agent-runtime = {
      image         = var.agent_runtime_image
      cpu           = 4096
      memory        = 8192
      desired_count = 3
      min_capacity  = 3
      max_capacity  = 16
      environment = merge(local.common_environment, { LUMI_ROLE = "agent-runtime" })
      secret_arns = {
        LUMI_DATABASE_URL          = local.secret_arns["database/app"]
        LUMI_REDIS_URL             = local.secret_arns["redis/url"]
        LUMI_RABBITMQ_URL          = local.secret_arns["rabbitmq/url"]
        LUMI_MODEL_PROVIDER_SECRET = local.secret_arns["providers/model"]
      }
      s3_bucket_arns         = [local.bucket_arns["assets"], local.bucket_arns["sandbox"]]
      autoscale_metric_name  = "AgentPendingRuns"
      autoscale_target_value = 8
    }

    model-gateway = {
      image         = var.model_gateway_image
      cpu           = 2048
      memory        = 4096
      desired_count = 3
      min_capacity  = 3
      max_capacity  = 12
      environment = merge(local.common_environment, { LUMI_ROLE = "model-gateway" })
      secret_arns = {
        LUMI_MODEL_PROVIDER_SECRET = local.secret_arns["providers/model"]
      }
      s3_bucket_arns         = []
      autoscale_metric_name  = "ModelGatewayInflight"
      autoscale_target_value = 50
    }

    tool-gateway = {
      image         = var.tool_gateway_image
      cpu           = 2048
      memory        = 4096
      desired_count = 3
      min_capacity  = 3
      max_capacity  = 12
      environment = merge(local.common_environment, { LUMI_ROLE = "tool-gateway" })
      secret_arns = {
        LUMI_DATABASE_URL        = local.secret_arns["database/app"]
        LUMI_AUTH_SIGNING_SECRET = local.secret_arns["auth/signing"]
      }
      s3_bucket_arns         = []
      autoscale_metric_name  = "ToolGatewayInflight"
      autoscale_target_value = 40
    }

    worker-media = {
      image         = var.worker_media_image
      cpu           = 4096
      memory        = 8192
      desired_count = 3
      min_capacity  = 3
      max_capacity  = 24
      environment = merge(local.common_environment, { LUMI_ROLE = "worker-media" })
      secret_arns = {
        LUMI_REDIS_URL             = local.secret_arns["redis/url"]
        LUMI_RABBITMQ_URL          = local.secret_arns["rabbitmq/url"]
        LUMI_MEDIA_PROVIDER_SECRET = local.secret_arns["providers/media"]
      }
      s3_bucket_arns         = [local.bucket_arns["assets"], local.bucket_arns["exports"]]
      autoscale_metric_name  = "MediaQueueBacklog"
      autoscale_target_value = 4
    }

    sandbox-runtime = {
      image         = var.sandbox_runtime_image
      cpu           = 2048
      memory        = 4096
      desired_count = 3
      min_capacity  = 3
      max_capacity  = 12
      environment = merge(local.common_environment, { LUMI_ROLE = "sandbox-runtime" })
      secret_arns = {
        LUMI_REDIS_URL    = local.secret_arns["redis/url"]
        LUMI_RABBITMQ_URL = local.secret_arns["rabbitmq/url"]
      }
      s3_bucket_arns         = [local.bucket_arns["sandbox"]]
      autoscale_metric_name  = "SandboxQueueBacklog"
      autoscale_target_value = 4
    }
  }
}

module "platform_app" {
  source = "../../../modules/platform-app"

  project                    = local.project
  environment                = local.environment
  vpc_id                     = local.core.vpc_id
  public_subnet_ids          = local.core.public_subnet_ids
  private_subnet_ids         = local.core.private_subnet_ids
  app_security_group_id      = local.core.app_security_group_id
  alb_security_group_id      = local.core.alb_security_group_id
  certificate_arn            = var.certificate_arn
  kms_key_arn                = local.core.kms_key_arn
  domain_name                = var.domain_name
  hosted_zone_id             = var.hosted_zone_id
  services                   = local.services
  waf_rate_limit_requests_per_5m = var.waf_rate_limit_requests_per_5m
  tags = {
    Owner       = "platform"
    DataClass   = "customer-production"
    ReleaseNode = "NODE-72"
  }
}

data "terraform_remote_state" "core" {
  backend = "s3"
  config = {
    bucket = var.core_state_bucket
    key    = var.core_state_key
    region = var.region
  }
}

locals {
  project      = "lumi"
  environment  = "staging"
  core         = data.terraform_remote_state.core.outputs
  secret_arns  = local.core.secret_arns
  bucket_arns  = local.core.bucket_arns
  bucket_names = local.core.bucket_names

  common_environment = {
    LUMI_ENV               = local.environment
    LUMI_REDIS_HOST        = local.core.redis_primary_endpoint
    LUMI_SERVICE_DISCOVERY = "staging.lumi.internal"
  }

  model_gateway_environment = {
    LUMI_MODEL_GATEWAY_URL = "http://model-gateway.${local.environment}.lumi.internal:8080"
  }

  tool_gateway_environment = {
    LUMI_TOOL_GATEWAY_URL = "http://tool-gateway.${local.environment}.lumi.internal:8080"
  }

  sandbox_runtime_environment = {
    LUMI_SANDBOX_RUNTIME_URL = "http://sandbox-runtime.${local.environment}.lumi.internal:8080"
  }

  side_effect_control_environment = {
    LUMI_SIDE_EFFECT_CONTROL_URL = "http://api.${local.environment}.lumi.internal:8000"
  }

  tool_audit_environment = {
    LUMI_TOOL_AUDIT_URL = "http://api.${local.environment}.lumi.internal:8000"
  }

  tool_approval_environment = {
    LUMI_TOOL_APPROVAL_URL = "http://api.${local.environment}.lumi.internal:8000"
  }

  tool_data_environment = {
    LUMI_TOOL_DATA_URL = "http://api.${local.environment}.lumi.internal:8000"
  }

  agent_control_environment = {
    LUMI_AGENT_CONTROL_URL = "http://api.${local.environment}.lumi.internal:8000"
  }

  services = {
    api = {
      image             = var.api_image
      cpu               = 1024
      memory            = 2048
      desired_count     = 2
      min_capacity      = 2
      max_capacity      = 6
      container_port    = 8000
      publicly_routed   = true
      health_check_path = "/health/ready"
      environment = merge(local.common_environment, { LUMI_ROLE = "api" })
      secret_arns = {
        LUMI_DATABASE_URL                    = local.secret_arns["database/app"]
        LUMI_REDIS_URL                       = local.secret_arns["redis/url"]
        LUMI_RABBITMQ_URL                    = local.secret_arns["rabbitmq/url"]
        LUMI_BILLING_WEBHOOK_SECRET          = local.secret_arns["billing/webhook"]
        LUMI_AUTH_SIGNING_SECRET             = local.secret_arns["auth/signing"]
        LUMI_SIDE_EFFECT_CONTROL_AUTH_SECRET = local.secret_arns["internal/side-effect-control"]
        LUMI_TOOL_AUDIT_AUTH_SECRET          = local.secret_arns["internal/tool-audit"]
        LUMI_TOOL_APPROVAL_AUTH_SECRET       = local.secret_arns["internal/tool-approval"]
        LUMI_TOOL_DATA_AUTH_SECRET           = local.secret_arns["internal/tool-data"]
        LUMI_AGENT_CONTROL_AUTH_SECRET       = local.secret_arns["internal/agent-control"]
      }
      s3_bucket_arns         = [local.bucket_arns["assets"], local.bucket_arns["exports"]]
      autoscale_metric_name  = "ApiConcurrentRequests"
      autoscale_target_value = 80
    }

    agent-runtime = {
      image         = var.agent_runtime_image
      cpu           = 2048
      memory        = 4096
      desired_count = 2
      min_capacity  = 2
      max_capacity  = 8
      environment = merge(
        local.common_environment,
        local.model_gateway_environment,
        local.tool_gateway_environment,
        local.agent_control_environment,
        { LUMI_ROLE = "agent-runtime" },
      )
      secret_arns = {
        LUMI_DATABASE_URL                = local.secret_arns["database/app"]
        LUMI_REDIS_URL                   = local.secret_arns["redis/url"]
        LUMI_RABBITMQ_URL                = local.secret_arns["rabbitmq/url"]
        LUMI_MODEL_GATEWAY_AUTH_SECRET   = local.secret_arns["internal/model-gateway"]
        LUMI_TOOL_GATEWAY_AUTH_SECRET    = local.secret_arns["internal/tool-gateway"]
        LUMI_AGENT_CONTROL_AUTH_SECRET   = local.secret_arns["internal/agent-control"]
      }
      s3_bucket_arns         = [local.bucket_arns["assets"], local.bucket_arns["sandbox"]]
      autoscale_metric_name  = "AgentPendingRuns"
      autoscale_target_value = 10
    }

    model-gateway = {
      image          = var.model_gateway_image
      cpu            = 1024
      memory         = 2048
      desired_count  = 2
      min_capacity   = 2
      max_capacity   = 6
      container_port = 8080
      environment = merge(
        local.common_environment,
        {
          LUMI_ROLE                   = "model-gateway"
          LUMI_PROVIDER_OUTPUT_BUCKET = local.bucket_names["assets"]
          LUMI_S3_REGION              = var.region
        },
      )
      secret_arns = {
        LUMI_DATABASE_URL              = local.secret_arns["database/app"]
        LUMI_MODEL_PROVIDER_SECRET     = local.secret_arns["providers/model"]
        LUMI_MEDIA_PROVIDER_SECRET     = local.secret_arns["providers/media"]
        LUMI_MODEL_GATEWAY_AUTH_SECRET = local.secret_arns["internal/model-gateway"]
      }
      s3_bucket_arns         = [local.bucket_arns["assets"]]
      autoscale_metric_name  = "ModelGatewayInflight"
      autoscale_target_value = 40
    }

    tool-gateway = {
      image          = var.tool_gateway_image
      cpu            = 1024
      memory         = 2048
      desired_count  = 2
      min_capacity   = 2
      max_capacity   = 6
      container_port = 8080
      environment = merge(
        local.common_environment,
        local.sandbox_runtime_environment,
        local.side_effect_control_environment,
        local.tool_audit_environment,
        local.tool_approval_environment,
        local.tool_data_environment,
        {
          LUMI_ROLE               = "tool-gateway"
          LUMI_TOOL_RESULT_BUCKET = local.bucket_names["exports"]
          LUMI_S3_REGION          = var.region
        },
      )
      secret_arns = {
        LUMI_DATABASE_URL                    = local.secret_arns["database/app"]
        LUMI_AUTH_SIGNING_SECRET             = local.secret_arns["auth/signing"]
        LUMI_TOOL_GATEWAY_AUTH_SECRET        = local.secret_arns["internal/tool-gateway"]
        LUMI_SANDBOX_RUNTIME_AUTH_SECRET     = local.secret_arns["internal/sandbox-runtime"]
        LUMI_SIDE_EFFECT_CONTROL_AUTH_SECRET = local.secret_arns["internal/side-effect-control"]
        LUMI_TOOL_AUDIT_AUTH_SECRET          = local.secret_arns["internal/tool-audit"]
        LUMI_TOOL_APPROVAL_AUTH_SECRET       = local.secret_arns["internal/tool-approval"]
        LUMI_TOOL_DATA_AUTH_SECRET           = local.secret_arns["internal/tool-data"]
        LUMI_BRAVE_SEARCH_API_KEY            = local.secret_arns["providers/search"]
      }
      s3_bucket_arns         = [local.bucket_arns["exports"]]
      autoscale_metric_name  = "ToolGatewayInflight"
      autoscale_target_value = 30
    }

    worker-media = {
      image         = var.worker_media_image
      cpu            = 2048
      memory         = 4096
      desired_count  = 2
      min_capacity   = 2
      max_capacity   = 12
      environment = merge(
        local.common_environment,
        local.model_gateway_environment,
        {
          LUMI_ROLE      = "worker-media"
          LUMI_S3_BUCKET = local.bucket_names["assets"]
          LUMI_S3_REGION = var.region
        },
      )
      secret_arns = {
        LUMI_DATABASE_URL              = local.secret_arns["database/app"]
        LUMI_REDIS_URL                 = local.secret_arns["redis/url"]
        LUMI_RABBITMQ_URL              = local.secret_arns["rabbitmq/url"]
        LUMI_MODEL_GATEWAY_AUTH_SECRET = local.secret_arns["internal/model-gateway"]
      }
      s3_bucket_arns         = [local.bucket_arns["assets"], local.bucket_arns["exports"]]
      autoscale_metric_name  = "MediaQueueBacklog"
      autoscale_target_value = 5
    }

    sandbox-runtime = {
      image          = var.sandbox_runtime_image
      cpu            = 1024
      memory         = 2048
      desired_count  = 2
      min_capacity   = 2
      max_capacity   = 6
      container_port = 8080
      environment = merge(local.common_environment, { LUMI_ROLE = "sandbox-runtime" })
      secret_arns = {
        LUMI_REDIS_URL                   = local.secret_arns["redis/url"]
        LUMI_RABBITMQ_URL                = local.secret_arns["rabbitmq/url"]
        LUMI_SANDBOX_RUNTIME_AUTH_SECRET = local.secret_arns["internal/sandbox-runtime"]
      }
      s3_bucket_arns         = [local.bucket_arns["sandbox"]]
      autoscale_metric_name  = "SandboxQueueBacklog"
      autoscale_target_value = 5
    }
  }
}

module "platform_app" {
  source = "../../../modules/platform-app"

  project                               = local.project
  environment                           = local.environment
  vpc_id                                = local.core.vpc_id
  public_subnet_ids                     = local.core.public_subnet_ids
  private_subnet_ids                     = local.core.private_subnet_ids
  app_security_group_id                  = local.core.app_security_group_id
  app_internet_egress_security_group_id = local.core.app_internet_egress_security_group_id
  sandbox_egress_security_group_id       = local.core.sandbox_egress_security_group_id
  alb_security_group_id                  = local.core.alb_security_group_id
  certificate_arn                        = var.certificate_arn
  kms_key_arn                            = local.core.kms_key_arn
  domain_name                            = var.domain_name
  hosted_zone_id                         = var.hosted_zone_id
  services                               = local.services
  waf_rate_limit_requests_per_5m         = var.waf_rate_limit_requests_per_5m
  tags = {
    Owner       = "platform"
    DataClass   = "synthetic-only"
    ReleaseNode = "NODE-72"
  }
}

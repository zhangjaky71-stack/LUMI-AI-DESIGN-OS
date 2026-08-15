locals {
  name = "${var.project}-${var.environment}"
  tags = merge(var.tags, {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  })
  public_services = {
    for name, service in var.services : name => service if service.publicly_routed
  }
  services_with_secrets = {
    for name, service in var.services : name => service if length(service.secret_arns) > 0
  }
  services_with_s3 = {
    for name, service in var.services : name => service if length(service.s3_bucket_arns) > 0
  }
}

resource "aws_ecs_cluster" "this" {
  name = "${local.name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.tags
}

resource "aws_service_discovery_private_dns_namespace" "this" {
  name        = "${var.environment}.lumi.internal"
  description = "Private service discovery namespace for ${local.name}"
  vpc         = var.vpc_id
  tags        = local.tags
}

resource "aws_service_discovery_service" "this" {
  for_each = var.services

  name = each.key

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.this.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "service" {
  for_each = var.services

  name              = "/lumi/${var.environment}/${each.key}"
  retention_in_days = var.environment == "production" ? 30 : 14
  kms_key_id        = var.kms_key_arn
  tags              = local.tags
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  for_each = var.services

  name               = "${local.name}-${each.key}-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  for_each = var.services

  role       = aws_iam_role.execution[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  for_each = local.services_with_secrets

  statement {
    sid       = "ReadDeclaredSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = values(each.value.secret_arns)
  }

  statement {
    sid       = "DecryptDeclaredSecrets"
    actions   = ["kms:Decrypt"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  for_each = local.services_with_secrets

  name   = "declared-secrets"
  role   = aws_iam_role.execution[each.key].id
  policy = data.aws_iam_policy_document.execution_secrets[each.key].json
}

resource "aws_iam_role" "task" {
  for_each = var.services

  name               = "${local.name}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "task_s3" {
  for_each = local.services_with_s3

  statement {
    sid = "DeclaredBucketMetadata"
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket",
    ]
    resources = each.value.s3_bucket_arns
  }

  statement {
    sid = "DeclaredObjectAccess"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [for arn in each.value.s3_bucket_arns : "${arn}/*"]
  }

  statement {
    sid       = "ApplicationDataKms"
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "task_s3" {
  for_each = local.services_with_s3

  name   = "declared-s3"
  role   = aws_iam_role.task[each.key].id
  policy = data.aws_iam_policy_document.task_s3[each.key].json
}

resource "aws_lb" "this" {
  name               = substr("${local.name}-alb", 0, 32)
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.environment == "production"
  drop_invalid_header_fields = true

  tags = local.tags
}

resource "aws_lb_target_group" "public" {
  for_each = local.public_services

  name        = substr("${local.name}-${each.key}", 0, 32)
  port        = each.value.container_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    path                = each.value.health_check_path
    protocol            = "HTTP"
    matcher             = "200-399"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
  }

  deregistration_delay = 30
  tags                 = local.tags
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = values(aws_lb_target_group.public)[0].arn
  }
}

resource "aws_ecs_task_definition" "service" {
  for_each = var.services

  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(each.value.cpu)
  memory                   = tostring(each.value.memory)
  execution_role_arn       = aws_iam_role.execution[each.key].arn
  task_role_arn            = aws_iam_role.task[each.key].arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    merge(
      {
        name      = each.key
        image     = each.value.image
        essential = true
        portMappings = [{
          containerPort = each.value.container_port
          hostPort      = each.value.container_port
          protocol      = "tcp"
        }]
        environment = [
          for key, value in each.value.environment : {
            name  = key
            value = value
          }
        ]
        secrets = [
          for key, arn in each.value.secret_arns : {
            name      = key
            valueFrom = arn
          }
        ]
        logConfiguration = {
          logDriver = "awslogs"
          options = {
            awslogs-group         = aws_cloudwatch_log_group.service[each.key].name
            awslogs-region        = data.aws_region.current.name
            awslogs-stream-prefix = each.key
          }
        }
      },
      length(each.value.command) > 0 ? { command = each.value.command } : {}
    )
  ])

  tags = local.tags
}

data "aws_region" "current" {}

resource "aws_ecs_service" "service" {
  for_each = var.services

  name            = each.key
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.service[each.key].arn
  desired_count   = each.value.desired_count
  launch_type     = "FARGATE"

  enable_execute_command = false
  propagate_tags         = "SERVICE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.this[each.key].arn
  }

  dynamic "load_balancer" {
    for_each = each.value.publicly_routed ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.public[each.key].arn
      container_name   = each.key
      container_port   = each.value.container_port
    }
  }

  depends_on = [aws_lb_listener.https]

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = local.tags
}

resource "aws_appautoscaling_target" "service" {
  for_each = var.services

  max_capacity       = each.value.max_capacity
  min_capacity       = each.value.min_capacity
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.service[each.key].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# LUMI emits queue/backlog/concurrency-aware custom metrics from NODE-67/69.
# This intentionally avoids CPU-only autoscaling for Agent/Media/SSE workloads.
resource "aws_appautoscaling_policy" "service_custom_metric" {
  for_each = var.services

  name               = "${local.name}-${each.key}-custom-metric"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.service[each.key].resource_id
  scalable_dimension = aws_appautoscaling_target.service[each.key].scalable_dimension
  service_namespace  = aws_appautoscaling_target.service[each.key].service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = each.value.autoscale_target_value
    scale_in_cooldown  = 180
    scale_out_cooldown = 60

    customized_metric_specification {
      metric_name = each.value.autoscale_metric_name
      namespace   = "LUMI/Capacity"
      statistic   = "Average"

      dimensions {
        name  = "Service"
        value = each.key
      }
    }
  }
}

locals {
  sandbox_runtime_config = try(var.services["sandbox-runtime"], null)
  sandbox_bucket_arn = local.sandbox_runtime_config == null ? null : try(
    local.sandbox_runtime_config.s3_bucket_arns[0],
    null,
  )
  sandbox_child_enabled = local.sandbox_runtime_config != null && local.sandbox_bucket_arn != null
  sandbox_bucket_name = local.sandbox_bucket_arn == null ? null : replace(
    local.sandbox_bucket_arn,
    "arn:aws:s3:::",
    "",
  )
}

resource "aws_cloudwatch_log_group" "sandbox_child" {
  count = local.sandbox_child_enabled ? 1 : 0

  name              = "/lumi/${var.environment}/sandbox-child"
  retention_in_days = var.environment == "production" ? 30 : 14
  kms_key_id        = var.kms_key_arn
  tags = merge(local.tags, {
    SecurityBoundary = "sandbox-child"
  })
}

resource "aws_iam_role" "sandbox_child_execution" {
  count = local.sandbox_child_enabled ? 1 : 0

  name               = "${local.name}-sandbox-child-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags = merge(local.tags, {
    SecurityBoundary = "sandbox-child"
  })
}

resource "aws_iam_role_policy_attachment" "sandbox_child_execution" {
  count = local.sandbox_child_enabled ? 1 : 0

  role       = aws_iam_role.sandbox_child_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "sandbox_child_task" {
  count = local.sandbox_child_enabled ? 1 : 0

  name               = "${local.name}-sandbox-child-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags = merge(local.tags, {
    SecurityBoundary = "sandbox-child"
  })
}

data "aws_iam_policy_document" "sandbox_child_exchange" {
  count = local.sandbox_child_enabled ? 1 : 0

  statement {
    sid = "SandboxExchangeBucketMetadata"
    actions = [
      "s3:GetBucketLocation",
    ]
    resources = [local.sandbox_bucket_arn]
  }

  statement {
    sid = "SandboxExchangeObjects"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${local.sandbox_bucket_arn}/sandbox-exchange/v1/*"]
  }

  statement {
    sid = "SandboxExchangeKms"
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey",
    ]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "sandbox_child_exchange" {
  count = local.sandbox_child_enabled ? 1 : 0

  name   = "sandbox-exchange-only"
  role   = aws_iam_role.sandbox_child_task[0].id
  policy = data.aws_iam_policy_document.sandbox_child_exchange[0].json
}

resource "aws_ecs_task_definition" "sandbox_child" {
  count = local.sandbox_child_enabled ? 1 : 0

  family                   = "${local.name}-sandbox-child"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.sandbox_child_execution[0].arn
  task_role_arn            = aws_iam_role.sandbox_child_task[0].arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "sandbox-child"
      image     = local.sandbox_runtime_config.image
      essential = true
      command   = ["lumi-sandbox-child"]
      environment = [
        {
          name  = "LUMI_SANDBOX_EXCHANGE_BUCKET"
          value = local.sandbox_bucket_name
        },
        {
          name  = "LUMI_ENV"
          value = var.environment
        },
      ]
      readonlyRootFilesystem = true
      linuxParameters = {
        initProcessEnabled = true
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.sandbox_child[0].name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = "sandbox-child"
        }
      }
    }
  ])

  tags = merge(local.tags, {
    SecurityBoundary = "sandbox-child"
    CustomerSecrets  = "none"
  })
}

data "aws_iam_policy_document" "sandbox_runtime_remote_control" {
  count = local.sandbox_child_enabled ? 1 : 0

  statement {
    sid = "RunOnlySandboxChildTask"
    actions = [
      "ecs:RunTask",
    ]
    resources = [aws_ecs_task_definition.sandbox_child[0].arn]
  }

  statement {
    sid = "ReadSandboxTaskState"
    actions = [
      "ecs:DescribeServices",
      "ecs:DescribeTaskDefinition",
      "ecs:DescribeTasks",
    ]
    resources = ["*"]
  }

  statement {
    sid = "PassOnlySandboxChildRoles"
    actions = [
      "iam:PassRole",
    ]
    resources = [
      aws_iam_role.sandbox_child_execution[0].arn,
      aws_iam_role.sandbox_child_task[0].arn,
    ]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "sandbox_runtime_remote_control" {
  count = local.sandbox_child_enabled ? 1 : 0

  name   = "remote-sandbox-child-control"
  role   = aws_iam_role.task["sandbox-runtime"].id
  policy = data.aws_iam_policy_document.sandbox_runtime_remote_control[0].json
}

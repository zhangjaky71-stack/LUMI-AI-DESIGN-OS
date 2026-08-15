resource "aws_cloudwatch_log_group" "migration" {
  name              = "/lumi/${var.environment}/migration"
  retention_in_days = var.environment == "production" ? 30 : 14
  kms_key_id        = var.kms_key_arn
  tags              = local.tags
}

resource "aws_iam_role" "migration_execution" {
  name               = "${local.name}-migration-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "migration_execution" {
  role       = aws_iam_role.migration_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "migration_execution_secret" {
  statement {
    sid       = "ReadMigrationDatabaseSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.migration_task.migration_secret_arn]
  }
  statement {
    sid       = "DecryptMigrationSecret"
    actions   = ["kms:Decrypt"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "migration_execution_secret" {
  name   = "migration-secret"
  role   = aws_iam_role.migration_execution.id
  policy = data.aws_iam_policy_document.migration_execution_secret.json
}

resource "aws_iam_role" "migration_task" {
  name               = "${local.name}-migration-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.tags
}

resource "aws_ecs_task_definition" "migration" {
  family                   = "${local.name}-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.migration_task.cpu)
  memory                   = tostring(var.migration_task.memory)
  execution_role_arn       = aws_iam_role.migration_execution.arn
  task_role_arn            = aws_iam_role.migration_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "migration"
      image     = var.migration_task.image
      essential = true
      command   = var.migration_task.command
      environment = [
        { name = "LUMI_ENV", value = var.environment },
      ]
      secrets = [
        {
          name      = "MIGRATION_DATABASE_URL"
          valueFrom = var.migration_task.migration_secret_arn
        },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.migration.name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = "migration"
        }
      }
    }
  ])

  tags = local.tags
}

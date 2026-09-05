data "terraform_remote_state" "core" {
  backend = "s3"
  config = {
    bucket = var.core_state_bucket
    key    = var.core_state_key
    region = var.region
  }
}

locals {
  name          = "lumi-staging-database-bootstrap"
  core          = data.terraform_remote_state.core.outputs
  database_name = "lumi"
  role_specs = {
    app = {
      role_name  = "lumi_app"
      secret_key = "database/app"
    }
    migration = {
      role_name  = "lumi_migration"
      secret_key = "database/migration"
    }
  }

  bootstrap_python = <<-PYCODE
import asyncio
import json
import os
from urllib.parse import unquote, urlsplit

import asyncpg

APP_ROLE = "lumi_app"
MIGRATION_ROLE = "lumi_migration"
DATABASE = os.environ["LUMI_DATABASE_NAME"]
HOST = os.environ["LUMI_POSTGRES_HOST"]
PORT = int(os.environ["LUMI_POSTGRES_PORT"])
RELEASE_SHA = os.environ["LUMI_RELEASE_GIT_SHA"]


def parse_role_url(value: str, expected_role: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    if parsed.scheme != "postgresql+asyncpg":
        raise RuntimeError(f"{expected_role} secret must use postgresql+asyncpg://")
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if username != expected_role or not password:
        raise RuntimeError(f"invalid database secret for {expected_role}")
    if parsed.hostname != HOST or parsed.port != PORT or parsed.path != f"/{DATABASE}":
        raise RuntimeError(f"database secret endpoint mismatch for {expected_role}")
    return username, password


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


async def connect(username: str, password: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        user=username,
        password=password,
        host=HOST,
        port=PORT,
        database=DATABASE,
        ssl="require",
        server_settings={"application_name": "lumi-staging-database-bootstrap"},
    )


async def main() -> None:
    master_secret = json.loads(os.environ["MASTER_SECRET_JSON"])
    master_user = master_secret.get("username")
    master_password = master_secret.get("password")
    if not isinstance(master_user, str) or not master_user or not isinstance(master_password, str) or not master_password:
        raise RuntimeError("RDS managed master secret is missing username/password")
    if master_user in {APP_ROLE, MIGRATION_ROLE}:
        raise RuntimeError("RDS master identity overlaps application identities")

    app_user, app_password = parse_role_url(os.environ["APP_DATABASE_URL"], APP_ROLE)
    migration_user, migration_password = parse_role_url(
        os.environ["MIGRATION_DATABASE_URL"], MIGRATION_ROLE
    )

    master = await connect(master_user, master_password)
    try:
        await master.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await master.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

        for role, password in (
            (APP_ROLE, app_password),
            (MIGRATION_ROLE, migration_password),
        ):
            exists = await master.fetchval(
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)", role
            )
            password_sql = quote_literal(password)
            if exists:
                await master.execute(f"ALTER ROLE {role} PASSWORD {password_sql}")
            else:
                await master.execute(f"CREATE ROLE {role} LOGIN PASSWORD {password_sql}")
            await master.execute(
                f"ALTER ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOBYPASSRLS NOINHERIT"
            )
            await master.execute(f"ALTER ROLE {role} SET search_path TO public")

        await master.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        await master.execute(f"GRANT CONNECT ON DATABASE {DATABASE} TO {APP_ROLE}")
        await master.execute(f"GRANT CONNECT ON DATABASE {DATABASE} TO {MIGRATION_ROLE}")
        await master.execute(f"REVOKE ALL ON SCHEMA public FROM {APP_ROLE}")
        await master.execute(f"REVOKE ALL ON SCHEMA public FROM {MIGRATION_ROLE}")
        await master.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
        await master.execute(f"GRANT USAGE, CREATE ON SCHEMA public TO {MIGRATION_ROLE}")
        await master.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATION_ROLE} IN SCHEMA public "
            f"GRANT SELECT ON TABLES TO {APP_ROLE}"
        )
        await master.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATION_ROLE} IN SCHEMA public "
            f"GRANT USAGE ON SEQUENCES TO {APP_ROLE}"
        )

        rows = await master.fetch(
            """
            SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls
            FROM pg_roles
            WHERE rolname = ANY($1::text[])
            ORDER BY rolname
            """,
            [APP_ROLE, MIGRATION_ROLE],
        )
        if {row["rolname"] for row in rows} != {APP_ROLE, MIGRATION_ROLE}:
            raise RuntimeError("database role creation is incomplete")
        for row in rows:
            if any(
                bool(row[field])
                for field in (
                    "rolsuper",
                    "rolcreaterole",
                    "rolcreatedb",
                    "rolreplication",
                    "rolbypassrls",
                )
            ):
                raise RuntimeError(f"privileged database role detected: {row['rolname']}")

        app_schema_create = await master.fetchval(
            "SELECT has_schema_privilege($1, 'public', 'CREATE')", APP_ROLE
        )
        migration_schema_create = await master.fetchval(
            "SELECT has_schema_privilege($1, 'public', 'CREATE')", MIGRATION_ROLE
        )
        app_db_create = await master.fetchval(
            "SELECT has_database_privilege($1, $2, 'CREATE')", APP_ROLE, DATABASE
        )
        migration_db_create = await master.fetchval(
            "SELECT has_database_privilege($1, $2, 'CREATE')", MIGRATION_ROLE, DATABASE
        )
        cross_membership = {
            "app_member_of_migration": bool(
                await master.fetchval("SELECT pg_has_role($1, $2, 'MEMBER')", APP_ROLE, MIGRATION_ROLE)
            ),
            "migration_member_of_app": bool(
                await master.fetchval("SELECT pg_has_role($1, $2, 'MEMBER')", MIGRATION_ROLE, APP_ROLE)
            ),
        }
        extensions = {
            row["extname"]
            for row in await master.fetch(
                "SELECT extname FROM pg_extension WHERE extname = ANY($1::text[])",
                ["vector", "pgcrypto"],
            )
        }
        if extensions != {"vector", "pgcrypto"}:
            raise RuntimeError("required PostgreSQL extensions are not installed")
        if app_schema_create or app_db_create or migration_db_create:
            raise RuntimeError("database role CREATE boundary is too broad")
        if not migration_schema_create:
            raise RuntimeError("migration role cannot create schema objects")
        if any(cross_membership.values()):
            raise RuntimeError("application and migration roles must not inherit each other")
    finally:
        await master.close()

    migration = await connect(migration_user, migration_password)
    try:
        await migration.execute(
            "CREATE TABLE public.__lumi_migration_privilege_probe (id integer PRIMARY KEY)"
        )
        await migration.execute("DROP TABLE public.__lumi_migration_privilege_probe")
    finally:
        await migration.close()

    app = await connect(app_user, app_password)
    app_create_denied = False
    try:
        try:
            await app.execute("CREATE TABLE public.__lumi_app_privilege_probe (id integer)")
        except asyncpg.InsufficientPrivilegeError:
            app_create_denied = True
        else:
            await app.execute("DROP TABLE public.__lumi_app_privilege_probe")
    finally:
        await app.close()
    if not app_create_denied:
        raise RuntimeError("application role unexpectedly created a table")

    evidence = {
        "schema_version": 1,
        "kind": "LUMI_STAGING_DATABASE_IDENTITY_BOOTSTRAP_V1",
        "status": "PASS",
        "release_git_sha": RELEASE_SHA,
        "database": DATABASE,
        "extensions": sorted(extensions),
        "roles": {
            APP_ROLE: {
                "login": True,
                "superuser": False,
                "create_role": False,
                "create_database": False,
                "replication": False,
                "bypass_rls": False,
                "schema_create": False,
                "create_probe_denied": app_create_denied,
            },
            MIGRATION_ROLE: {
                "login": True,
                "superuser": False,
                "create_role": False,
                "create_database": False,
                "replication": False,
                "bypass_rls": False,
                "schema_create": True,
                "create_probe_passed": True,
            },
        },
        "cross_membership": cross_membership,
        "master_role_distinct": master_user not in {APP_ROLE, MIGRATION_ROLE},
    }
    print("LUMI_DB_IDENTITY_EVIDENCE=" + json.dumps(evidence, sort_keys=True, separators=(",", ":")))


asyncio.run(main())
PYCODE
}

ephemeral "random_password" "database_role" {
  for_each = local.role_specs

  length      = 48
  special     = false
  min_upper   = 8
  min_lower   = 8
  min_numeric = 8
}

resource "aws_secretsmanager_secret_version" "database_role" {
  for_each = local.role_specs

  secret_id = local.core.secret_arns[each.value.secret_key]
  secret_string_wo = format(
    "postgresql+asyncpg://%s:%s@%s:%s/%s",
    each.value.role_name,
    ephemeral.random_password.database_role[each.key].result,
    local.core.postgres_endpoint,
    local.core.postgres_port,
    local.database_name,
  )
  secret_string_wo_version = var.credential_generation
}

resource "aws_security_group" "database_bootstrap_egress" {
  name        = "${local.name}-egress"
  description = "One-shot database bootstrap may reach only the Staging PostgreSQL security group."
  vpc_id      = local.core.vpc_id

  egress {
    description     = "PostgreSQL only"
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [local.core.postgres_security_group_id]
  }

  tags = {
    Project          = "lumi"
    Environment      = "staging"
    ManagedBy        = "terraform"
    Purpose          = "database-identity-bootstrap"
    SecurityBoundary = "postgres-only-egress"
  }
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

resource "aws_ecs_cluster" "database_bootstrap" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "database_bootstrap" {
  name              = "/lumi/staging/database-bootstrap"
  retention_in_days = 30
  kms_key_id        = local.core.kms_key_arn
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid     = "ReadOnlyDatabaseBootstrapSecrets"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      local.core.postgres_master_secret_arn,
      local.core.secret_arns["database/app"],
      local.core.secret_arns["database/migration"],
    ]
  }

  statement {
    sid       = "DecryptLumiManagedSecrets"
    actions   = ["kms:Decrypt"]
    resources = [local.core.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "database-bootstrap-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_ecs_task_definition" "database_bootstrap" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "database-bootstrap"
      image     = var.api_image
      essential = true
      command   = ["python", "-c", local.bootstrap_python]
      environment = [
        { name = "LUMI_DATABASE_NAME", value = local.database_name },
        { name = "LUMI_POSTGRES_HOST", value = local.core.postgres_endpoint },
        { name = "LUMI_POSTGRES_PORT", value = tostring(local.core.postgres_port) },
        { name = "LUMI_RELEASE_GIT_SHA", value = var.release_git_sha },
      ]
      secrets = [
        { name = "MASTER_SECRET_JSON", valueFrom = local.core.postgres_master_secret_arn },
        { name = "APP_DATABASE_URL", valueFrom = local.core.secret_arns["database/app"] },
        { name = "MIGRATION_DATABASE_URL", valueFrom = local.core.secret_arns["database/migration"] },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.database_bootstrap.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "database-bootstrap"
        }
      }
    }
  ])

  depends_on = [
    aws_secretsmanager_secret_version.database_role,
    aws_iam_role_policy.execution_secrets,
  ]
}

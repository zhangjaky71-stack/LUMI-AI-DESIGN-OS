from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IAC = ROOT / "infra/iac/environments/staging/database-bootstrap"
MAIN = IAC / "main.tf"
VARIABLES = IAC / "variables.tf"
VERSIONS = IAC / "versions.tf"
OUTPUTS = IAC / "outputs.tf"
RUNNER = ROOT / "scripts/ecs-run-database-bootstrap-task.sh"
API_PROJECT = ROOT / "apps/api/pyproject.toml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Staging database identity contract invalid: {message}")


def main() -> int:
    for path in (MAIN, VARIABLES, VERSIONS, OUTPUTS, RUNNER, API_PROJECT):
        require(path.is_file(), f"missing {path.relative_to(ROOT)}")

    main_tf = MAIN.read_text(encoding="utf-8")
    variables = VARIABLES.read_text(encoding="utf-8")
    versions = VERSIONS.read_text(encoding="utf-8")
    outputs = OUTPUTS.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    api_project = API_PROJECT.read_text(encoding="utf-8")

    require('"asyncpg==0.31.0"' in api_project, "frozen API runtime must contain asyncpg")
    require('ephemeral "random_password" "database_role"' in main_tf, "database passwords must be ephemeral")
    require("secret_string_wo" in main_tf, "database secrets must use Secrets Manager write-only values")
    require("secret_string =" not in main_tf, "database passwords must not enter ordinary Terraform state")
    require('"database/app"' in main_tf and '"database/migration"' in main_tf, "both database secret boundaries are required")
    require("postgres_master_secret_arn" in main_tf, "one-shot task must bind the AWS-managed RDS master secret")
    require("lumi_app" in main_tf and "lumi_migration" in main_tf, "fixed app/migration roles are required")
    for marker in ("NOSUPERUSER", "NOCREATEDB", "NOCREATEROLE", "NOREPLICATION", "NOBYPASSRLS"):
        require(marker in main_tf, f"missing role hardening marker {marker}")
    require("REVOKE CREATE ON SCHEMA public FROM PUBLIC" in main_tf, "public schema CREATE must be revoked")
    require("GRANT USAGE ON SCHEMA public TO" in main_tf, "application schema USAGE is required")
    require("GRANT USAGE, CREATE ON SCHEMA public TO" in main_tf, "migration schema CREATE is required")
    require("CREATE EXTENSION IF NOT EXISTS vector" in main_tf, "vector extension must be pre-installed with master trust")
    require("CREATE EXTENSION IF NOT EXISTS pgcrypto" in main_tf, "pgcrypto extension must be pre-installed with master trust")
    require("LUMI_DB_IDENTITY_EVIDENCE=" in main_tf, "one-shot task must emit sanitized identity evidence")

    require('description     = "PostgreSQL only"' in main_tf, "bootstrap egress must be PostgreSQL-only")
    require("from_port       = 5432" in main_tf and "to_port         = 5432" in main_tf, "bootstrap egress must be port 5432 only")
    require("postgres_security_group_id" in main_tf, "bootstrap egress must target PostgreSQL SG")
    require('cidr_blocks = ["0.0.0.0/0"]' not in main_tf, "database bootstrap must not have public egress")
    require("app_internet_egress_security_group_id" not in main_tf, "database bootstrap must not attach public internet egress")

    require('actions = ["secretsmanager:GetSecretValue"]' in main_tf, "execution role must read only scoped database bootstrap secrets")
    require('"kms:Decrypt"' in main_tf, "execution role must decrypt LUMI-managed database secrets")
    require("secretsmanager:*" not in main_tf and "kms:*" not in main_tf, "database bootstrap IAM must not use wildcard secret/KMS actions")

    require('version = "= 6.55.0"' in versions, "AWS provider must remain pinned")
    require('version = "= 3.9.0"' in versions, "random provider must remain pinned")
    require("allowed_account_ids = [var.account_id]" in versions, "provider account allow-list is required")
    require("lumi-staging-api@sha256:" in variables, "API image must be an immutable Staging ECR digest")
    require("release_git_sha" in variables and "[0-9a-f]{40}" in variables, "exact release SHA variable is required")

    required_outputs = (
        "database_bootstrap_task_definition_arn",
        "database_bootstrap_network",
        "database_bootstrap_log_group_name",
        "database_role_secret_arns",
        "database_bootstrap_api_image",
        "database_bootstrap_release_git_sha",
    )
    for name in required_outputs:
        require(f'output "{name}"' in outputs, f"missing Terraform output {name}")

    require("aws ecs run-task" in runner and "aws ecs wait tasks-stopped" in runner, "runner must execute and wait for Fargate task")
    require("assignPublicIp=DISABLED" in runner, "database bootstrap task must not receive a public IP")
    require("get-log-events" in runner, "runner must capture sanitized task evidence from CloudWatch")
    require("list-secret-version-ids" in runner, "runner must bind secret version ids without reading values")
    require("get-secret-value" not in runner, "GitHub runner must never retrieve database secret values")
    require("LUMI_STAGING_DATABASE_IDENTITY_BOOTSTRAP_V1" in runner, "runner must verify inner database evidence schema")
    require("LUMI_STAGING_DATABASE_IDENTITY_RUN_V1" in runner, "runner must emit outer immutable run evidence")

    print("Staging database identity bootstrap contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

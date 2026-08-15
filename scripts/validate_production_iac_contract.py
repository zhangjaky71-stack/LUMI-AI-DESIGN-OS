#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        raise SystemExit(f"production IaC contract invalid: missing {path}")
    return target.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"production IaC contract invalid: {message}")


def main() -> int:
    required_roots = [
        "infra/iac/environments/staging/core/main.tf",
        "infra/iac/environments/staging/migration/main.tf",
        "infra/iac/environments/staging/app/main.tf",
        "infra/iac/environments/production/core/main.tf",
        "infra/iac/environments/production/migration/main.tf",
        "infra/iac/environments/production/app/main.tf",
    ]
    for path in required_roots:
        text(path)

    network = text("infra/iac/modules/network/main.tf")
    compute = text("infra/iac/modules/compute/main.tf")
    data = text("infra/iac/modules/data/main.tf")
    storage = text("infra/iac/modules/storage/main.tf")
    secrets = text("infra/iac/modules/secrets/main.tf")
    migration = text("infra/iac/modules/migration-runner/main.tf")
    bootstrap = text("infra/iac/bootstrap/main.tf")
    staging_app = text("infra/iac/environments/staging/app/main.tf")
    production_app = text("infra/iac/environments/production/app/main.tf")
    production_core_vars = text("infra/iac/environments/production/core/variables.tf")
    alembic_env = text("apps/api/alembic/env.py")
    production_workflow = text(".github/workflows/deploy-production.yml")
    ecs_evidence = text("scripts/capture-ecs-deployment-state.sh")

    require("assign_public_ip = false" in compute, "ECS services must not receive public IPs")
    require("internal           = false" in compute, "public ALB contract missing")
    require("wait_for_steady_state  = true" in compute, "Terraform must wait for ECS steady state")
    require("deployment_circuit_breaker" in compute and "rollback = true" in compute, "rolling-service rollback missing")
    require('strategy             = "CANARY"' in compute, "public ECS canary strategy missing")
    require("canary_percent" in compute and "canary_bake_time_in_minutes" in compute, "canary percentage/bake configuration missing")
    require("public_alternate" in compute and "advanced_configuration" in compute, "alternate target group canary routing missing")
    require("AmazonECSInfrastructureRolePolicyForLoadBalancers" in compute, "ECS load-balancer infrastructure role missing")
    require("public_canary_5xx" in compute and "public_canary_unhealthy" in compute, "canary rollback alarms missing")
    require("from_port       = 8000" in network and "to_port         = 8000" in network, "ALB-to-API security group port must be 8000")
    require("container_port    = 8000" in staging_app and "container_port    = 8000" in production_app, "API container port must match lumi_api CLI port 8000")
    require("publicly_accessible = false" in data, "RDS must be private")
    require("multi_az" in data, "RDS Multi-AZ contract missing")
    require("transit_encryption_enabled = true" in data, "Redis transit encryption missing")
    require("at_rest_encryption_enabled = true" in data, "Redis at-rest encryption missing")
    require('deployment_mode = "CLUSTER_MULTI_AZ"' in data, "RabbitMQ Multi-AZ contract missing")
    require("block_public_acls       = true" in storage and "restrict_public_buckets = true" in storage, "S3 public-access block incomplete")
    require('status = "Enabled"' in storage, "S3 versioning contract missing")
    require("aws:SecureTransport" in storage, "S3 TLS-only policy missing")
    require("aws_secretsmanager_secret_version" not in secrets, "secret values must not be written by Terraform")
    require("MIGRATION_DATABASE_URL" in migration, "migration task must inject migration-only database credential")
    require("aws_ecs_service" not in migration, "migration runner must be one-shot, not an ECS service")
    require("pg_try_advisory_lock" in alembic_env and "pg_advisory_unlock" in alembic_env, "Alembic advisory migration lock missing")
    require("environment:production" in bootstrap and "token.actions.githubusercontent.com:aud" in bootstrap, "production GitHub OIDC subject/audience contract missing")
    require("assign_public_ip = true" not in network + compute + migration, "public task IP configuration detected")
    require("migration_task" not in production_app, "migration must remain a separate Terraform stack from app services")
    require("length(var.availability_zones) == 3" in production_core_vars, "production must require three availability zones")
    require("capture-ecs-deployment-state.sh" in production_workflow, "production workflow must archive ECS steady-state evidence")
    require("running_count == .desired_count" in ecs_evidence and "pending_count == 0" in ecs_evidence, "ECS evidence script must verify counts")

    version_files = [ROOT / "infra/iac/bootstrap/versions.tf", *ROOT.glob("infra/iac/environments/**/versions.tf")]
    for version_file in version_files:
        body = version_file.read_text(encoding="utf-8")
        require('version = "= 6.55.0"' in body, f"AWS provider is not exactly pinned in {version_file.relative_to(ROOT)}")
        require('required_version = ">= 1.14.6, < 1.15.0"' in body, f"Terraform CLI contract is not pinned in {version_file.relative_to(ROOT)}")

    for example in ROOT.glob("infra/iac/environments/**/terraform.tfvars.example"):
        body = example.read_text(encoding="utf-8").lower()
        require("password =" not in body and "auth_token =" not in body, f"secret-like value found in {example.relative_to(ROOT)}")

    print("production IaC contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

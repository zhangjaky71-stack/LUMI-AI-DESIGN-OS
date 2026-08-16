from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(path: str, *needles: str) -> None:
    text = read(path)
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{path} missing final hard-stop contracts: {missing}")


def main() -> int:
    for environment in ("staging", "production"):
        app_path = f"infra/iac/environments/{environment}/app/main.tf"
        require(
            app_path,
            'model-gateway = {',
            'LUMI_DATABASE_URL          = local.secret_arns["database/app"]',
            'sandbox-runtime = {',
            "isolated_network = true",
            "isolated_subnet_ids        = local.core.data_subnet_ids",
            "sandbox_security_group_id  = local.core.sandbox_security_group_id",
        )
        app_output_path = f"infra/iac/environments/{environment}/app/outputs.tf"
        require(
            app_output_path,
            'output "deployment_alert_topic_arn"',
            'output "deployment_alert_evidence_queue_url"',
        )
        core_output_path = f"infra/iac/environments/{environment}/core/outputs.tf"
        require(
            core_output_path,
            'output "sandbox_security_group_id"',
            "module.platform_core.sandbox_security_group_id",
        )

    require(
        "infra/iac/modules/network/main.tf",
        '# Data/isolated subnets deliberately have NO Internet/NAT default route.',
        'resource "aws_security_group" "sandbox"',
        'cidr_blocks = [var.vpc_cidr]',
        'prefix_list_ids = [data.aws_prefix_list.s3.id]',
        'resource "aws_vpc_endpoint" "sandbox_interface"',
        '"ecr.api"',
        '"ecr.dkr"',
        '"logs"',
        '"secretsmanager"',
        '"kms"',
        'resource "aws_vpc_endpoint" "s3"',
    )
    network = read("infra/iac/modules/network/main.tf")
    sandbox_block = network.split(
        'resource "aws_security_group" "sandbox"', 1
    )[1].split('resource "aws_security_group" "sandbox_endpoints"', 1)[0]
    if 'cidr_blocks = ["0.0.0.0/0"]' in sandbox_block:
        raise AssertionError("sandbox security group must not have Internet egress")
    data_routes = network.split('resource "aws_route_table" "data"', 1)[1].split(
        'resource "aws_route_table_association" "data"', 1
    )[0]
    if 'cidr_block = "0.0.0.0/0"' in data_routes:
        raise AssertionError("isolated data route tables must not have a default route")

    require(
        "infra/iac/modules/compute/main.tf",
        "each.value.isolated_network ? var.isolated_subnet_ids : var.private_subnet_ids",
        "each.value.isolated_network ? var.sandbox_security_group_id : var.app_security_group_id",
        "assign_public_ip = false",
        'resource "aws_cloudwatch_metric_alarm" "public_canary_5xx"',
        'resource "aws_cloudwatch_metric_alarm" "public_canary_unhealthy"',
        "rollback = true",
    )
    require(
        "infra/iac/modules/compute/variables.tf",
        'variable "isolated_subnet_ids"',
        'variable "sandbox_security_group_id"',
        "isolated_network         = optional(bool, false)",
        'error_message = "sandbox-runtime must use isolated_network=true."',
    )
    alerting = read("infra/iac/modules/compute/alerting.tf")
    require(
        "infra/iac/modules/compute/alerting.tf",
        'data "aws_iam_policy_document" "deployment_alert_kms"',
        'resource "aws_kms_key" "deployment_alerts"',
        '"cloudwatch.amazonaws.com"',
        '"events.amazonaws.com"',
        '"kms:GenerateDataKey*"',
        '"kms:Decrypt"',
        'resource "aws_sns_topic" "deployment_alerts"',
        "kms_master_key_id = aws_kms_key.deployment_alerts.arn",
        'resource "aws_sqs_queue" "deployment_alert_evidence"',
        'resource "aws_sns_topic_subscription" "deployment_alert_evidence"',
        'resource "aws_cloudwatch_composite_alarm" "public_deployment"',
        "alarm_actions     = [aws_sns_topic.deployment_alerts.arn]",
        "ok_actions        = [aws_sns_topic.deployment_alerts.arn]",
        'resource "aws_cloudwatch_event_rule" "ecs_deployment_failure"',
        '"SERVICE_DEPLOYMENT_FAILED"',
    )
    eventbridge_publish = alerting.split('sid       = "EventBridgePublish"', 1)[1].split(
        "  }\n}\n\nresource \"aws_sns_topic_policy\"", 1
    )[0]
    if "condition {" in eventbridge_publish:
        raise AssertionError(
            "EventBridge -> SNS topic-policy statement must not contain a Condition block"
        )
    require(
        "infra/iac/bootstrap/main.tf",
        '"cloudwatch:*"',
        '"events:*"',
        '"sns:*"',
        '"sqs:*"',
        '"ecs:*"',
    )

    data = read("infra/iac/modules/data/main.tf")
    require(
        "infra/iac/modules/data/main.tf",
        "var.sandbox_security_group_id",
        'resource "aws_security_group" "postgres"',
        'resource "aws_security_group" "redis"',
        'resource "aws_security_group" "rabbitmq"',
    )
    postgres_block = data.split(
        'resource "aws_security_group" "postgres"', 1
    )[1].split('resource "aws_security_group" "redis"', 1)[0]
    if "var.sandbox_security_group_id" in postgres_block:
        raise AssertionError("sandbox must not be trusted by PostgreSQL security group")

    require(
        "services/model-gateway/src/lumi_model_gateway/gateway.py",
        '_PRODUCTION_LIKE_ENVIRONMENTS = frozenset({"production", "staging"})',
        "DurableBudgetGuardRequiredError",
        "budget_guard is None or isinstance(budget_guard, RequestBudgetGuard)",
        '"RequestBudgetGuard is development-only"',
    )
    require(
        "apps/api/src/lumi_api/costs/model_gateway_factory.py",
        "build_durable_model_budget_guard",
        'os.getenv("LUMI_DATABASE_URL")',
        "LedgerBudgetGuard(PostgresModelCostAccounting(dsn))",
    )
    require(
        "apps/api/alembic/versions/0018_provider_daily_cost_hard_stop.py",
        "provider_daily_hard_stop_enabled boolean NOT NULL DEFAULT false",
        "provider_daily_cost_limits",
        "budget_day_utc",
        "pg_advisory_xact_lock",
        "COST_PROVIDER_DAILY_BUDGET_EXCEEDED",
    )

    deploy = read(".github/workflows/deploy-production.yml")
    require(
        ".github/workflows/deploy-production.yml",
        "Initialize production app for rollback baseline",
        "Freeze pre-deployment ECS rollback target",
        "predeploy-ecs-state.json",
        "Create and wait for pre-deployment RDS snapshot",
    )
    if deploy.index("Freeze pre-deployment ECS rollback target") > deploy.index(
        "Create and wait for pre-deployment RDS snapshot"
    ):
        raise AssertionError("ECS rollback target must be frozen before production mutation")

    require(
        "scripts/alert-delivery-drill.sh",
        "put-metric-alarm",
        'wait_alarm_state "ALARM"',
        'wait_delivery "ALARM"',
        'wait_alarm_state "OK"',
        'wait_delivery "OK"',
        '"passed: true"',
    )
    require(
        "scripts/ecs-rollback-to-state.sh",
        "describe-task-definition",
        "update-service",
        "aws ecs wait services-stable",
        "database_downgrade_attempted: false",
        "target_restored",
    )
    require(
        ".github/workflows/final-operational-drills.yml",
        "environment: production",
        "ALERT_DRILL:${DEPLOYMENT_ID}",
        "ROLLBACK_PRODUCTION:${DEPLOYMENT_ID}:${DEPLOYMENT_RUN_ID}",
        "actions/download-artifact@v4",
        "predeploy-ecs-state.json",
        "scripts/ecs-rollback-to-state.sh",
        "scripts/alert-delivery-drill.sh",
    )
    require(
        "docs/operations/ROLLBACK-AND-ALERT-DRILLS.md",
        "SOURCE_IMPLEMENTED / VALIDATION_PENDING",
        "human on-call",
        "First production bootstrap",
        "Terraform reconciliation after emergency rollback",
    )

    print(
        "Final provider-budget, sandbox-egress, rollback, and alert-delivery source contracts: PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

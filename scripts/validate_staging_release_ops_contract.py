#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEPLOY = ROOT / ".github/workflows/deploy-staging-infrastructure.yml"
BRIDGE = ROOT / ".github/workflows/release-staging-dispatch-bridge.yml"
PREFLIGHT = ROOT / "scripts/validate_staging_environment_preflight.py"
REGISTRY = ROOT / "infra/iac/modules/container-registry/main.tf"
PLATFORM_MAIN = ROOT / "infra/iac/modules/platform-core/main.tf"
PLATFORM_OUTPUTS = ROOT / "infra/iac/modules/platform-core/outputs.tf"
STAGING_MAIN = ROOT / "infra/iac/environments/staging/core/main.tf"
STAGING_VARS = ROOT / "infra/iac/environments/staging/core/variables.tf"
STAGING_VERSIONS = ROOT / "infra/iac/environments/staging/core/versions.tf"
STAGING_TFVARS = ROOT / "infra/iac/environments/staging/core/terraform.tfvars.example"
STAGING_OUTPUTS = ROOT / "infra/iac/environments/staging/core/outputs.tf"
PRODUCTION_OUTPUTS = ROOT / "infra/iac/environments/production/core/outputs.tf"
PINS = ROOT / "production/release-actions/pins-v1.json"

PINNED_ACTIONS = {
    "actions/checkout": "d23441a48e516b6c34aea4fa41551a30e30af803",
    "hashicorp/setup-terraform": "dfe3c3f87815947d99a8997f908cb6525fc44e9e",
    "aws-actions/configure-aws-credentials": "e6de054238d6b7531b4efff3b6587d9aade6a06c",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
}

EXPECTED_GENERATED_INTERNAL_SECRETS = {
    "auth/signing",
    "internal/model-gateway",
    "internal/tool-gateway",
    "internal/sandbox-runtime",
    "internal/side-effect-control",
    "internal/tool-audit",
    "internal/tool-approval",
    "internal/tool-data",
    "internal/agent-control",
}


def require(text: str, marker: str, label: str) -> None:
    if marker not in text:
        raise SystemExit(f"{label} missing required marker: {marker}")


def reject(text: str, marker: str, label: str) -> None:
    if marker in text:
        raise SystemExit(f"{label} contains forbidden marker: {marker}")


def parse_toset_string_block(text: str, assignment: str) -> set[str]:
    marker = f"{assignment} = toset(["
    start = text.find(marker)
    if start < 0:
        raise SystemExit(f"missing set assignment: {assignment}")
    start += len(marker)
    end = text.find("])\n", start)
    if end < 0:
        raise SystemExit(f"unterminated set assignment: {assignment}")
    values: set[str] = set()
    for raw in text[start:end].splitlines():
        value = raw.strip().rstrip(",")
        if not value:
            continue
        if not (value.startswith('"') and value.endswith('"')):
            raise SystemExit(f"{assignment} contains non-literal entry: {raw!r}")
        values.add(value[1:-1])
    return values


def main() -> int:
    deploy = DEPLOY.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")
    preflight = PREFLIGHT.read_text(encoding="utf-8")
    registry = REGISTRY.read_text(encoding="utf-8")
    platform_main = PLATFORM_MAIN.read_text(encoding="utf-8")
    platform_outputs = PLATFORM_OUTPUTS.read_text(encoding="utf-8")
    staging_main = STAGING_MAIN.read_text(encoding="utf-8")
    staging_vars = STAGING_VARS.read_text(encoding="utf-8")
    staging_versions = STAGING_VERSIONS.read_text(encoding="utf-8")
    staging_tfvars = STAGING_TFVARS.read_text(encoding="utf-8")
    staging_outputs = STAGING_OUTPUTS.read_text(encoding="utf-8")
    production_outputs = PRODUCTION_OUTPUTS.read_text(encoding="utf-8")
    pins = json.loads(PINS.read_text(encoding="utf-8"))

    compile(preflight, str(PREFLIGHT), "exec")

    for action, sha in PINNED_ACTIONS.items():
        require(deploy, f"{action}@{sha}", "deploy-staging-infrastructure")
    require(bridge, f"actions/checkout@{PINNED_ACTIONS['actions/checkout']}", "release-staging-dispatch-bridge")

    for marker in (
        "promote-runtime-images",
        "--preserve-digests",
        "--all",
        "runtime_image_set_artifact_digest",
        "LUMI_STAGING_RUNTIME_IMAGE_PROMOTION_V1",
        "promoted_image_set_json",
        "TF_VAR_video_model_profile",
        "destination_manifest_raw_digest",
        "digest_preserved",
        "ImageNotFoundException",
        "Validate protected Staging environment preflight",
        "python3 scripts/validate_staging_environment_preflight.py",
        "AWS_DEPLOY_ROLE_ARN: ${{ vars.AWS_DEPLOY_ROLE_ARN }}",
    ):
        require(deploy, marker, "deploy-staging-infrastructure")

    preflight_step = deploy.find("Validate protected Staging environment preflight")
    aws_step = deploy.find("aws-actions/configure-aws-credentials@")
    if preflight_step < 0 or aws_step < 0 or preflight_step >= aws_step:
        raise SystemExit("Staging environment preflight must execute before AWS credential configuration")

    for stale in (
        "vars.API_IMAGE_DIGEST",
        "vars.AGENT_RUNTIME_IMAGE_DIGEST",
        "vars.MODEL_GATEWAY_IMAGE_DIGEST",
        "vars.TOOL_GATEWAY_IMAGE_DIGEST",
        "vars.WORKER_MEDIA_IMAGE_DIGEST",
        "vars.SANDBOX_RUNTIME_IMAGE_DIGEST",
        "TF_VAR_redis_auth_token",
        "TF_VAR_rabbitmq_username",
        "TF_VAR_rabbitmq_password",
        "secrets.REDIS_AUTH_TOKEN",
        "secrets.RABBITMQ_USERNAME",
        "secrets.RABBITMQ_PASSWORD",
        "continue-on-error",
    ):
        reject(deploy, stale, "deploy-staging-infrastructure")

    for marker in (
        '"kind": "LUMI_STAGING_ENVIRONMENT_PREFLIGHT_V1"',
        '"secret_values_recorded": False',
        '"plan-core", "apply-core"',
        '"plan-migration", "apply-migration", "run-migration"',
        '"plan-app", "apply-app"',
        'operation == "promote-runtime-images"',
        '"AWS_DEPLOY_ROLE_ARN"',
        '"TF_STATE_BUCKET"',
        '"TF_VAR_account_id"',
        '"TF_VAR_availability_zones"',
        '"TF_VAR_certificate_arn"',
        '"TF_VAR_hosted_zone_id"',
        '"VIDEO_MODEL_PROFILE_INPUT"',
        '"VIDEO_MODEL_PROFILE_DEFAULT"',
        'return 0 if payload["status"] == "PASS" else 64',
    ):
        require(preflight, marker, "Staging environment preflight")

    for marker in (
        'resource "aws_ecr_repository" "runtime"',
        'image_tag_mutability = "IMMUTABLE"',
        "scan_on_push = true",
        'encryption_type = "AES256"',
        "force_delete         = false",
    ):
        require(registry, marker, "container-registry")

    require(platform_main, 'module "container_registry"', "platform-core")
    require(platform_outputs, 'output "runtime_repository_urls"', "platform-core outputs")
    require(staging_outputs, 'output "runtime_repository_urls"', "staging core outputs")
    require(production_outputs, 'output "runtime_repository_urls"', "production core outputs")

    for marker in (
        'source  = "hashicorp/random"',
        'version = "= 3.9.0"',
    ):
        require(staging_versions, marker, "staging core providers")

    for marker in (
        'resource "random_password" "redis_auth_token"',
        'resource "random_password" "rabbitmq_password"',
        'rabbitmq_username = "lumi_app"',
        'module.platform_core.secret_arns["redis/url"]',
        'module.platform_core.secret_arns["rabbitmq/url"]',
        'secret_string_wo = format(',
        'secret_string_wo = replace(',
        "secret_string_wo_version = 1",
        '"rediss://:%s@%s:6379/0"',
        '"amqps://${local.rabbitmq_username}:${random_password.rabbitmq_password.result}@"',
        'ephemeral "random_password" "internal_secret"',
        'resource "aws_secretsmanager_secret_version" "internal_secret"',
        "secret_string_wo         = ephemeral.random_password.internal_secret[each.key].result",
    ):
        require(staging_main, marker, "staging core generated infrastructure secrets")

    generated_internal = parse_toset_string_block(staging_main, "generated_internal_secret_names")
    if generated_internal != EXPECTED_GENERATED_INTERNAL_SECRETS:
        raise SystemExit(
            "generated internal secret set mismatch: "
            f"expected={sorted(EXPECTED_GENERATED_INTERNAL_SECRETS)!r} actual={sorted(generated_internal)!r}"
        )

    for stale in (
        'variable "redis_auth_token"',
        'variable "rabbitmq_username"',
        'variable "rabbitmq_password"',
    ):
        reject(staging_vars, stale, "staging core variables")

    for stale in (
        "TF_VAR_redis_auth_token",
        "TF_VAR_rabbitmq_username",
        "TF_VAR_rabbitmq_password",
    ):
        reject(staging_tfvars, stale, "staging core tfvars example")

    for marker in (
        "production/staging/release-request-v1.json",
        "deploy-staging-infrastructure.yml/dispatches",
        "return_run_details",
        "node-73-staging-",
        "APPLY_STAGING",
    ):
        require(bridge, marker, "release-staging-dispatch-bridge")

    critical = set(pins.get("release_critical_workflows", []))
    evidence = set(pins.get("release_evidence_workflows", []))
    governed = critical | evidence
    canonical_deploy = ".github/workflows/deploy-staging-infrastructure.yml"
    if canonical_deploy not in governed:
        raise SystemExit("release action pin policy must govern canonical Staging deploy workflow")
    if canonical_deploy in critical:
        raise SystemExit("Staging deploy must remain outside the fixed default-branch dispatch-critical registry")
    non_dispatch_helpers = {
        ".github/workflows/release-staging-dispatch-bridge.yml",
        ".github/workflows/staging-release-ops-contract.yml",
    }
    unexpected = sorted(non_dispatch_helpers & critical)
    if unexpected:
        raise SystemExit("push-only Staging helpers must not enter the workflow_dispatch critical registry: " + ", ".join(unexpected))

    print(
        json.dumps(
            {
                "status": "PASS",
                "kind": "LUMI_STAGING_RELEASE_OPS_CONTRACT_V1",
                "runtime_repository_count": 6,
                "digest_preserving_promotion": True,
                "stale_image_vars_rejected": True,
                "canonical_deploy_action_pin_governed": True,
                "environment_preflight_before_aws_oidc": True,
                "environment_preflight_secret_values_recorded": False,
                "stale_manual_credential_env_rejected": True,
                "generated_staging_infrastructure_credentials": True,
                "write_only_runtime_connection_secret_versions": True,
                "manual_staging_redis_rabbitmq_tfvars_rejected": True,
                "ephemeral_internal_secret_count": len(EXPECTED_GENERATED_INTERNAL_SECRETS),
                "external_provider_and_database_secrets_not_synthesized": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

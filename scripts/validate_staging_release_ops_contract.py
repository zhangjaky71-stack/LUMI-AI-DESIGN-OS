#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEPLOY = ROOT / ".github/workflows/deploy-staging-infrastructure.yml"
BRIDGE = ROOT / ".github/workflows/release-staging-dispatch-bridge.yml"
REGISTRY = ROOT / "infra/iac/modules/container-registry/main.tf"
PLATFORM_MAIN = ROOT / "infra/iac/modules/platform-core/main.tf"
PLATFORM_OUTPUTS = ROOT / "infra/iac/modules/platform-core/outputs.tf"
STAGING_OUTPUTS = ROOT / "infra/iac/environments/staging/core/outputs.tf"
PRODUCTION_OUTPUTS = ROOT / "infra/iac/environments/production/core/outputs.tf"
PINS = ROOT / "production/release-actions/pins-v1.json"

PINNED_ACTIONS = {
    "actions/checkout": "d23441a48e516b6c34aea4fa41551a30e30af803",
    "hashicorp/setup-terraform": "dfe3c3f87815947d99a8997f908cb6525fc44e9e",
    "aws-actions/configure-aws-credentials": "e6de054238d6b7531b4efff3b6587d9aade6a06c",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
}


def require(text: str, marker: str, label: str) -> None:
    if marker not in text:
        raise SystemExit(f"{label} missing required marker: {marker}")


def reject(text: str, marker: str, label: str) -> None:
    if marker in text:
        raise SystemExit(f"{label} contains forbidden marker: {marker}")


def main() -> int:
    deploy = DEPLOY.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")
    registry = REGISTRY.read_text(encoding="utf-8")
    platform_main = PLATFORM_MAIN.read_text(encoding="utf-8")
    platform_outputs = PLATFORM_OUTPUTS.read_text(encoding="utf-8")
    staging_outputs = STAGING_OUTPUTS.read_text(encoding="utf-8")
    production_outputs = PRODUCTION_OUTPUTS.read_text(encoding="utf-8")
    pins = json.loads(PINS.read_text(encoding="utf-8"))

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
    ):
        require(deploy, marker, "deploy-staging-infrastructure")

    for stale in (
        "vars.API_IMAGE_DIGEST",
        "vars.AGENT_RUNTIME_IMAGE_DIGEST",
        "vars.MODEL_GATEWAY_IMAGE_DIGEST",
        "vars.TOOL_GATEWAY_IMAGE_DIGEST",
        "vars.WORKER_MEDIA_IMAGE_DIGEST",
        "vars.SANDBOX_RUNTIME_IMAGE_DIGEST",
        "continue-on-error",
    ):
        reject(deploy, stale, "deploy-staging-infrastructure")

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
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

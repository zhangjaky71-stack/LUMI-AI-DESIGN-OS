#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import runpy
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "scripts" / "production-deployment-gate.py"
CAPACITY_CONTRACT_PATH = ROOT / "scripts" / "validate_capacity_autoscaling_contract.py"
MANIFEST_TEMPLATE_PATH = ROOT / "production" / "deployment" / "manifest-template.json"


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_production_deployment_gate", GATE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit("unable to import production deployment gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"production deployment contract invalid: {message}")


def clean_manifest(acceptance_path: str) -> dict[str, Any]:
    digest = "sha256:" + "d" * 64
    return {
        "schema_version": 1,
        "deployment_id": "prod-contract-001",
        "environment": "production",
        "release_candidate": {
            "git_sha": "c" * 40,
            "version": "1.0.0-rc.1",
            "migration_head": "20260815_001",
            "staging_acceptance_decision_id": "acceptance-contract-001",
            "staging_acceptance_run_id": "123",
            "staging_acceptance_path": acceptance_path,
        },
        "aws": {
            "account_id": "123456789012",
            "region": "ap-northeast-1",
            "production_role_arn": "arn:aws:iam::123456789012:role/lumi-production-deployer",
        },
        "edge": {
            "domain": "app.example.com",
            "certificate_arn": "arn:aws:acm:ap-northeast-1:123456789012:certificate/11111111-2222-3333-4444-555555555555",
            "waf_enabled": True,
            "https_only": True,
        },
        "images": {
            name: f"123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/lumi-{name}@{digest}"
            for name in [
                "api",
                "agent-runtime",
                "model-gateway",
                "tool-gateway",
                "worker-media",
                "sandbox-runtime",
            ]
        },
        "rollout": {
            "public_api_strategy": "ECS_CANARY",
            "public_api_canary_percent": 5,
            "public_api_canary_bake_minutes": 10,
            "public_api_alarm_rollback": True,
            "internal_service_strategy": "ROLLING_CIRCUIT_BREAKER",
        },
        "recovery": {
            "database_pitr_max_rpo_minutes": 5,
            "database_pitr_max_rto_minutes": 60,
            "object_version_recovery_required": True,
        },
        "first_day_limits": {
            "max_org_concurrent_agent_runs": 4,
            "max_org_concurrent_generations": 4,
            "max_org_concurrent_video_jobs": 1,
            "daily_provider_spend_usd": 100,
            "invite_rate_per_hour": 20,
        },
        "rollback": {
            "previous_deployment_id": "prod-previous-001",
            "previous_manifest_ref": (
                "reports/production-deployments/prod-previous-001/manifest.json"
            ),
            "database_backward_compatible": True,
        },
        "external_dependencies": {
            "dns": "READY",
            "email_domain": "READY",
            "billing_provider": "READY",
            "model_provider": "READY",
            "support_on_call": "READY",
        },
        "approvals": {
            "staging_acceptance": "APPROVED",
            "engineering": "APPROVED",
            "security": "APPROVED",
            "release_owner": "APPROVED",
        },
    }


def clean_decision(images: dict[str, str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "decision_id": "acceptance-contract-001",
        "passed": True,
        "release_candidate": {
            "git_sha": "c" * 40,
            "version": "1.0.0-rc.1",
            "migration_head": "20260815_001",
        },
        "container_image_set": {
            "images": copy.deepcopy(images),
            "provenance": {},
        },
    }


def main() -> int:
    require(CAPACITY_CONTRACT_PATH.is_file(), "capacity autoscaling contract missing")
    runpy.run_path(str(CAPACITY_CONTRACT_PATH), run_name="__main__")

    gate = load_gate()
    acceptance_path = Path(gate.CANONICAL_STAGING_ACCEPTANCE_PATH)
    clean = clean_manifest(acceptance_path.as_posix())
    decision = clean_decision(clean["images"])

    template = json.loads(MANIFEST_TEMPLATE_PATH.read_text(encoding="utf-8"))
    require(
        template["release_candidate"]["staging_acceptance_run_id"] == "PENDING",
        "production manifest template must require explicit NODE-71 run identity",
    )
    require(
        template["release_candidate"]["staging_acceptance_path"]
        == gate.CANONICAL_STAGING_ACCEPTANCE_PATH.as_posix(),
        "production manifest template must use the canonical downloaded NODE-71 decision path",
    )
    require(
        template["first_day_limits"]["daily_provider_spend_usd"] == 100,
        "production manifest template must encode the $100 provider hard stop",
    )
    require(
        template["recovery"]
        == {
            "database_pitr_max_rpo_minutes": 5,
            "database_pitr_max_rto_minutes": 60,
            "object_version_recovery_required": True,
        },
        "production manifest template must encode the canonical launch recovery policy",
    )

    gate_source = GATE_PATH.read_text(encoding="utf-8")
    for marker in (
        'parser.add_argument("--acceptance-provenance", required=True)',
        'parser.add_argument("--acceptance-run-id", required=True)',
        'parser.add_argument("--repository", required=True)',
        "_validate_node71_artifact(",
        "production manifest staging_acceptance_run_id differs from requested NODE-71 run",
    ):
        require(marker in gate_source, f"production gate missing NODE-71 artifact binding marker: {marker}")

    result = gate.evaluate(clean, decision, acceptance_path)
    require(result["passed"] is True, "clean contract fixture must pass")

    invalid_run_id = copy.deepcopy(clean)
    invalid_run_id["release_candidate"]["staging_acceptance_run_id"] = "PENDING"
    require(
        gate.evaluate(invalid_run_id, decision, acceptance_path)["passed"] is False,
        "missing NODE-71 run id must block",
    )

    run_id_zero = copy.deepcopy(clean)
    run_id_zero["release_candidate"]["staging_acceptance_run_id"] = "0"
    require(
        gate.evaluate(run_id_zero, decision, acceptance_path)["passed"] is False,
        "zero NODE-71 run id must block",
    )

    path_swap = copy.deepcopy(clean)
    path_swap["release_candidate"]["staging_acceptance_path"] = (
        "reports/staging-acceptance/manual/decision.json"
    )
    require(
        gate.evaluate(path_swap, decision, acceptance_path)["passed"] is False,
        "manual NODE-71 decision path must block",
    )

    not_accepted = copy.deepcopy(decision)
    not_accepted["passed"] = False
    require(
        gate.evaluate(clean, not_accepted, acceptance_path)["passed"] is False,
        "NODE-71 passed=false must block",
    )

    sha_swap = copy.deepcopy(decision)
    sha_swap["release_candidate"]["git_sha"] = "e" * 40
    require(
        gate.evaluate(clean, sha_swap, acceptance_path)["passed"] is False,
        "accepted SHA mismatch must block",
    )

    migration_swap = copy.deepcopy(clean)
    migration_swap["release_candidate"]["migration_head"] = "different-head"
    require(
        gate.evaluate(migration_swap, decision, acceptance_path)["passed"] is False,
        "migration-head mismatch must block",
    )

    mutable_image = copy.deepcopy(clean)
    mutable_image["images"]["api"] = "example.invalid/lumi-api:latest"
    require(
        gate.evaluate(mutable_image, decision, acceptance_path)["passed"] is False,
        "mutable image tag must block",
    )

    accepted_image_swap = copy.deepcopy(clean)
    accepted_image_swap["images"]["model-gateway"] = (
        "123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/"
        "lumi-model-gateway@sha256:" + "e" * 64
    )
    require(
        gate.evaluate(accepted_image_swap, decision, acceptance_path)["passed"] is False,
        "production must not replace a NODE-71 accepted image with another valid digest",
    )

    rollout_swap = copy.deepcopy(clean)
    rollout_swap["rollout"]["public_api_canary_percent"] = 100
    require(
        gate.evaluate(rollout_swap, decision, acceptance_path)["passed"] is False,
        "all-at-once public rollout must block",
    )

    relaxed_rpo = copy.deepcopy(clean)
    relaxed_rpo["recovery"]["database_pitr_max_rpo_minutes"] = 30
    require(
        gate.evaluate(relaxed_rpo, decision, acceptance_path)["passed"] is False,
        "release must not relax the 5-minute launch RPO policy",
    )

    relaxed_rto = copy.deepcopy(clean)
    relaxed_rto["recovery"]["database_pitr_max_rto_minutes"] = 240
    require(
        gate.evaluate(relaxed_rto, decision, acceptance_path)["passed"] is False,
        "release must not relax the 60-minute launch RTO policy",
    )

    object_recovery_disabled = copy.deepcopy(clean)
    object_recovery_disabled["recovery"]["object_version_recovery_required"] = False
    require(
        gate.evaluate(object_recovery_disabled, decision, acceptance_path)["passed"] is False,
        "release must not disable object version recovery rehearsal",
    )

    provider_spend_above_hard_stop = copy.deepcopy(clean)
    provider_spend_above_hard_stop["first_day_limits"]["daily_provider_spend_usd"] = 100.01
    require(
        gate.evaluate(provider_spend_above_hard_stop, decision, acceptance_path)["passed"]
        is False,
        "production provider spend limit above $100 must block",
    )

    no_rollback = copy.deepcopy(clean)
    no_rollback["rollback"]["database_backward_compatible"] = False
    require(
        gate.evaluate(no_rollback, decision, acceptance_path)["passed"] is False,
        "unproven DB rollback compatibility must block",
    )

    external_pending = copy.deepcopy(clean)
    external_pending["external_dependencies"]["dns"] = "PENDING"
    require(
        gate.evaluate(external_pending, decision, acceptance_path)["passed"] is False,
        "pending core external dependency must block",
    )

    missing_approval = copy.deepcopy(clean)
    missing_approval["approvals"]["security"] = "PENDING"
    require(
        gate.evaluate(missing_approval, decision, acceptance_path)["passed"] is False,
        "missing security approval must block",
    )

    print(
        json.dumps(
            {
                "status": "PASS",
                "clean_gate_id": result["gate_id"],
                "drills": {
                    "node71_run_id_missing_blocked": True,
                    "node71_run_id_zero_blocked": True,
                    "manual_node71_path_blocked": True,
                    "node71_artifact_cli_binding_required": True,
                    "node71_not_passed_blocked": True,
                    "accepted_sha_swap_blocked": True,
                    "migration_swap_blocked": True,
                    "mutable_image_blocked": True,
                    "accepted_image_swap_blocked": True,
                    "all_at_once_rollout_blocked": True,
                    "recovery_rpo_relaxation_blocked": True,
                    "recovery_rto_relaxation_blocked": True,
                    "object_recovery_disable_blocked": True,
                    "provider_spend_above_100_blocked": True,
                    "db_rollback_unproven_blocked": True,
                    "external_pending_blocked": True,
                    "missing_approval_blocked": True,
                    "unmeasured_autoscaling_blocked": True
                }
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "scripts" / "production-deployment-gate.py"


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
            for name in ["api", "agent-runtime", "model-gateway", "tool-gateway", "worker-media", "sandbox-runtime"]
        },
        "rollout": {
            "public_api_strategy": "ECS_CANARY",
            "public_api_canary_percent": 5,
            "public_api_canary_bake_minutes": 10,
            "public_api_alarm_rollback": True,
            "internal_service_strategy": "ROLLING_CIRCUIT_BREAKER",
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
            "previous_manifest_ref": "reports/production-deployments/prod-previous-001/manifest.json",
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


def clean_decision() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "decision_id": "acceptance-contract-001",
        "passed": True,
        "release_candidate": {
            "git_sha": "c" * 40,
            "version": "1.0.0-rc.1",
            "migration_head": "20260815_001",
        },
    }


def main() -> int:
    gate = load_gate()
    acceptance_path = Path("reports/staging-acceptance/contract/decision.json")
    clean = clean_manifest(acceptance_path.as_posix())
    decision = clean_decision()
    result = gate.evaluate(clean, decision, acceptance_path)
    require(result["passed"] is True, "clean contract fixture must pass")

    not_accepted = copy.deepcopy(decision)
    not_accepted["passed"] = False
    require(gate.evaluate(clean, not_accepted, acceptance_path)["passed"] is False, "NODE-71 passed=false must block")

    sha_swap = copy.deepcopy(decision)
    sha_swap["release_candidate"]["git_sha"] = "e" * 40
    require(gate.evaluate(clean, sha_swap, acceptance_path)["passed"] is False, "accepted SHA mismatch must block")

    migration_swap = copy.deepcopy(clean)
    migration_swap["release_candidate"]["migration_head"] = "different-head"
    require(gate.evaluate(migration_swap, decision, acceptance_path)["passed"] is False, "migration-head mismatch must block")

    mutable_image = copy.deepcopy(clean)
    mutable_image["images"]["api"] = "example.invalid/lumi-api:latest"
    require(gate.evaluate(mutable_image, decision, acceptance_path)["passed"] is False, "mutable image tag must block")

    rollout_swap = copy.deepcopy(clean)
    rollout_swap["rollout"]["public_api_canary_percent"] = 100
    require(gate.evaluate(rollout_swap, decision, acceptance_path)["passed"] is False, "all-at-once public rollout must block")

    provider_spend_above_hard_stop = copy.deepcopy(clean)
    provider_spend_above_hard_stop["first_day_limits"]["daily_provider_spend_usd"] = 100.01
    require(
        gate.evaluate(provider_spend_above_hard_stop, decision, acceptance_path)["passed"] is False,
        "production provider spend limit above $100 must block",
    )

    no_rollback = copy.deepcopy(clean)
    no_rollback["rollback"]["database_backward_compatible"] = False
    require(gate.evaluate(no_rollback, decision, acceptance_path)["passed"] is False, "unproven DB rollback compatibility must block")

    external_pending = copy.deepcopy(clean)
    external_pending["external_dependencies"]["dns"] = "PENDING"
    require(gate.evaluate(external_pending, decision, acceptance_path)["passed"] is False, "pending core external dependency must block")

    missing_approval = copy.deepcopy(clean)
    missing_approval["approvals"]["security"] = "PENDING"
    require(gate.evaluate(missing_approval, decision, acceptance_path)["passed"] is False, "missing security approval must block")

    print(json.dumps({
        "status": "PASS",
        "clean_gate_id": result["gate_id"],
        "drills": {
            "node71_not_passed_blocked": True,
            "accepted_sha_swap_blocked": True,
            "migration_swap_blocked": True,
            "mutable_image_blocked": True,
            "all_at_once_rollout_blocked": True,
            "provider_spend_above_100_blocked": True,
            "db_rollback_unproven_blocked": True,
            "external_pending_blocked": True,
            "missing_approval_blocked": True
        }
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

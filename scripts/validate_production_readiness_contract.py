#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_GATE = ROOT / "scripts" / "production-rollback-gate.py"
ROLLBACK_DECISION = ROOT / "scripts" / "production-rollback-rehearsal-decision.py"
DEPLOYMENT_DECISION = ROOT / "scripts" / "production-deployment-decision.py"

IMAGE_KEYS = [
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
]
SERVICE_IMAGE_KEY = {
    "api": "api",
    "agent-runtime": "agent-runtime",
    "model-gateway": "model-gateway",
    "tool-gateway": "tool-gateway",
    "worker-media": "worker-media",
    "outbox-dispatcher": "worker-media",
    "sandbox-runtime": "sandbox-runtime",
}
CAPACITY_CONTRACT_SOURCE = "terraform-live-state"
CAPACITY_CONTRACT_SCOPE = "production-app-service-desired-counts"


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"production readiness contract invalid: {message}")


def images(seed: str) -> dict[str, str]:
    return {
        name: f"123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/lumi-{name}@sha256:{seed * 64}"
        for name in IMAGE_KEYS
    }


def service_capacity(service: str) -> int:
    return 2 if service == "outbox-dispatcher" else 3


def manifest(*, deployment_id: str, version: str, sha: str, image_seed: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "deployment_id": deployment_id,
        "environment": "production",
        "release_candidate": {
            "git_sha": sha,
            "version": version,
            "migration_head": "0020_generation_operation_identity",
            "staging_acceptance_decision_id": "staging-pass",
            "staging_acceptance_path": "reports/staging-acceptance/rc/decision.json",
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
        "images": images(image_seed),
        "rollout": {
            "public_api_strategy": "ECS_CANARY",
            "public_api_canary_percent": 5,
            "public_api_canary_bake_minutes": 10,
            "public_api_alarm_rollback": True,
            "internal_service_strategy": "ROLLING_CIRCUIT_BREAKER",
        },
    }


def runtime(
    value: dict[str, Any],
    *,
    capacity_contract_deployment_id: str | None = None,
) -> dict[str, Any]:
    counts = {service: service_capacity(service) for service in SERVICE_IMAGE_KEY}
    return {
        "schema_version": 1,
        "deployment_id": value["deployment_id"],
        "release_candidate": {
            key: value["release_candidate"][key]
            for key in ("git_sha", "version", "migration_head")
        },
        "cluster_arn": "arn:aws:ecs:ap-northeast-1:123456789012:cluster/lumi-production",
        "capacity_contract": {
            "schema_version": 1,
            "source": CAPACITY_CONTRACT_SOURCE,
            "scope": CAPACITY_CONTRACT_SCOPE,
            "deployment_id": capacity_contract_deployment_id or value["deployment_id"],
            "service_desired_counts": copy.deepcopy(counts),
        },
        "passed": True,
        "services": [
            {
                "service_name": service,
                "image_key": image_key,
                "task_definition": f"arn:aws:ecs:task-definition/{service}:1",
                "image": value["images"][image_key],
                "expected_image": value["images"][image_key],
                "image_matches": True,
                "status": "ACTIVE",
                "rollout_state": "COMPLETED",
                "expected_desired_count": counts[service],
                "desired_count": counts[service],
                "running_count": counts[service],
                "pending_count": 0,
                "capacity_matches": True,
                "steady": True,
            }
            for service, image_key in SERVICE_IMAGE_KEY.items()
        ],
    }


def smoke(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "passed": True,
        "base_url": f"https://{value['edge']['domain']}",
        "results": {
            "/health/live": {"status": 200},
            "/health/ready": {"status": 200},
            "/version": {"status": 200, "version": value["release_candidate"]["version"]},
        },
    }


def rollout(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "deployment_id": value["deployment_id"],
        "release_candidate": {
            key: value["release_candidate"][key]
            for key in ("git_sha", "version", "migration_head")
        },
        "strategy": "CANARY",
        "canary_percent": 5,
        "bake_time_minutes": 10,
        "canary_bake_time_minutes": 10,
        "alarms_enabled": True,
        "alarms_rollback": True,
        "alternate_target_group_arn": "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:targetgroup/green/1",
        "production_listener_rule": "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:listener-rule/app/lumi/1/2/3",
        "alarms": [
            {"name": "canary-5xx", "state": "OK"},
            {"name": "canary-unhealthy", "state": "OK"},
        ],
        "passed": True,
    }


def main() -> int:
    rollback_gate = load_module(ROLLBACK_GATE, "lumi_rollback_contract")
    rollback_decision = load_module(ROLLBACK_DECISION, "lumi_rollback_decision_contract")
    deployment_decision = load_module(DEPLOYMENT_DECISION, "lumi_deployment_decision_contract")

    previous_path = Path("reports/production-deployments/prod-prev/manifest.json")
    current = manifest(deployment_id="prod-current", version="1.1.0", sha="c" * 40, image_seed="c")
    previous = manifest(deployment_id="prod-prev", version="1.0.0", sha="b" * 40, image_seed="b")
    current["rollback"] = {
        "previous_deployment_id": previous["deployment_id"],
        "previous_manifest_ref": previous_path.as_posix(),
        "database_backward_compatible": True,
    }

    gate = rollback_gate.evaluate(current, previous, previous_path)
    require(gate["passed"] is True, "clean rollback relationship must pass")

    cross_account = copy.deepcopy(previous)
    cross_account["aws"]["account_id"] = "999999999999"
    require(
        rollback_gate.evaluate(current, cross_account, previous_path)["passed"] is False,
        "cross-account rollback must block",
    )
    db_unsafe = copy.deepcopy(current)
    db_unsafe["rollback"]["database_backward_compatible"] = False
    require(
        rollback_gate.evaluate(db_unsafe, previous, previous_path)["passed"] is False,
        "unproven database compatibility must block rollback",
    )
    mutable_previous = copy.deepcopy(previous)
    mutable_previous["images"]["api"] = "example.invalid/lumi-api:latest"
    require(
        rollback_gate.evaluate(current, mutable_previous, previous_path)["passed"] is False,
        "mutable rollback image must block",
    )

    previous_runtime = runtime(
        previous,
        capacity_contract_deployment_id=current["deployment_id"],
    )
    previous_smoke = smoke(previous)
    restored_runtime = runtime(current)
    restored_smoke = smoke(current)
    rehearsal = rollback_decision.evaluate(
        current,
        previous,
        previous_path,
        previous_runtime,
        previous_smoke,
        restored_runtime,
        restored_smoke,
        [{"path": "fixture", "sha256": "a" * 64}],
    )
    require(rehearsal["passed"] is True, "clean rollback+roll-forward rehearsal must pass")
    require(
        rehearsal["capacity_contract"]["current_infrastructure_deployment_id"]
        == current["deployment_id"],
        "rollback rehearsal must bind capacity to current infrastructure deployment",
    )
    require(
        rehearsal["capacity_contract"]["preserved_across_image_rollback"] is True,
        "rollback rehearsal must prove capacity preservation",
    )

    wrong_previous_capacity_owner = copy.deepcopy(previous_runtime)
    wrong_previous_capacity_owner["capacity_contract"]["deployment_id"] = previous["deployment_id"]
    require(
        rollback_decision.evaluate(
            current,
            previous,
            previous_path,
            wrong_previous_capacity_owner,
            previous_smoke,
            restored_runtime,
            restored_smoke,
            [],
        )["passed"]
        is False,
        "rollback target capacity must remain bound to current infrastructure",
    )

    forged_previous_capacity_map = copy.deepcopy(previous_runtime)
    forged_previous_capacity_map["capacity_contract"]["service_desired_counts"]["outbox-dispatcher"] += 1
    require(
        rollback_decision.evaluate(
            current,
            previous,
            previous_path,
            forged_previous_capacity_map,
            previous_smoke,
            restored_runtime,
            restored_smoke,
            [],
        )["passed"]
        is False,
        "rollback target forged capacity map must block",
    )

    wrong_restored_image = copy.deepcopy(restored_runtime)
    wrong_restored_image["services"][0]["image"] = previous["images"]["api"]
    require(
        rollback_decision.evaluate(
            current,
            previous,
            previous_path,
            previous_runtime,
            previous_smoke,
            wrong_restored_image,
            restored_smoke,
            [],
        )["passed"]
        is False,
        "roll-forward with wrong runtime image must block",
    )
    wrong_dispatcher_image = copy.deepcopy(restored_runtime)
    dispatcher = next(
        item
        for item in wrong_dispatcher_image["services"]
        if item["service_name"] == "outbox-dispatcher"
    )
    dispatcher["image"] = current["images"]["api"]
    dispatcher["image_matches"] = False
    require(
        rollback_decision.evaluate(
            current,
            previous,
            previous_path,
            previous_runtime,
            previous_smoke,
            wrong_dispatcher_image,
            restored_smoke,
            [],
        )["passed"]
        is False,
        "outbox dispatcher must remain bound to worker-media image during roll-forward",
    )
    wrong_dispatcher_capacity = copy.deepcopy(restored_runtime)
    dispatcher = next(
        item
        for item in wrong_dispatcher_capacity["services"]
        if item["service_name"] == "outbox-dispatcher"
    )
    dispatcher["desired_count"] = dispatcher["expected_desired_count"] + 1
    dispatcher["running_count"] = dispatcher["desired_count"]
    dispatcher["capacity_matches"] = True
    dispatcher["steady"] = True
    require(
        rollback_decision.evaluate(
            current,
            previous,
            previous_path,
            previous_runtime,
            previous_smoke,
            wrong_dispatcher_capacity,
            restored_smoke,
            [],
        )["passed"]
        is False,
        "roll-forward must reject dispatcher capacity drift even if booleans are forged true",
    )

    wrong_restored_capacity_owner = copy.deepcopy(restored_runtime)
    wrong_restored_capacity_owner["capacity_contract"]["deployment_id"] = previous["deployment_id"]
    require(
        rollback_decision.evaluate(
            current,
            previous,
            previous_path,
            previous_runtime,
            previous_smoke,
            wrong_restored_capacity_owner,
            restored_smoke,
            [],
        )["passed"]
        is False,
        "roll-forward capacity contract must be bound to current infrastructure",
    )

    wrong_previous_version = copy.deepcopy(previous_smoke)
    wrong_previous_version["results"]["/version"]["version"] = "wrong"
    require(
        rollback_decision.evaluate(
            current,
            previous,
            previous_path,
            previous_runtime,
            wrong_previous_version,
            restored_runtime,
            restored_smoke,
            [],
        )["passed"]
        is False,
        "rollback target smoke version mismatch must block",
    )

    deployment_gate = {
        "schema_version": 1,
        "deployment_id": current["deployment_id"],
        "release_candidate": current["release_candidate"],
        "passed": True,
    }
    snapshot = {
        "schema_version": 1,
        "deployment_id": current["deployment_id"],
        "status": "available",
        "passed": True,
    }
    migration = {
        "schema_version": 1,
        "deployment_id": current["deployment_id"],
        "exit_code": 0,
        "passed": True,
    }
    live_rollout = rollout(current)
    final = deployment_decision.evaluate(
        current,
        deployment_gate,
        snapshot,
        migration,
        restored_runtime,
        live_rollout,
        restored_smoke,
        rehearsal,
        [{"path": "fixture", "sha256": "a" * 64}],
    )
    require(final["passed"] is True, "clean production deployment decision must pass")
    require(
        final["capacity_contract"]["deployment_id"] == current["deployment_id"],
        "deployment decision must freeze current capacity contract identity",
    )

    bad_runtime_dispatcher = copy.deepcopy(restored_runtime)
    dispatcher = next(
        item
        for item in bad_runtime_dispatcher["services"]
        if item["service_name"] == "outbox-dispatcher"
    )
    dispatcher["image"] = current["images"]["sandbox-runtime"]
    dispatcher["expected_image"] = current["images"]["sandbox-runtime"]
    require(
        deployment_decision.evaluate(
            current,
            deployment_gate,
            snapshot,
            migration,
            bad_runtime_dispatcher,
            live_rollout,
            restored_smoke,
            rehearsal,
            [],
        )["passed"]
        is False,
        "production decision must block dispatcher image-key substitution",
    )

    bad_runtime_capacity = copy.deepcopy(restored_runtime)
    dispatcher = next(
        item
        for item in bad_runtime_capacity["services"]
        if item["service_name"] == "outbox-dispatcher"
    )
    dispatcher["desired_count"] = dispatcher["expected_desired_count"] + 1
    dispatcher["running_count"] = dispatcher["desired_count"]
    dispatcher["capacity_matches"] = True
    dispatcher["steady"] = True
    require(
        deployment_decision.evaluate(
            current,
            deployment_gate,
            snapshot,
            migration,
            bad_runtime_capacity,
            live_rollout,
            restored_smoke,
            rehearsal,
            [],
        )["passed"]
        is False,
        "production decision must block Terraform capacity drift even if evidence booleans are forged true",
    )

    bad_runtime_capacity_contract = copy.deepcopy(restored_runtime)
    bad_runtime_capacity_contract["capacity_contract"]["deployment_id"] = previous["deployment_id"]
    require(
        deployment_decision.evaluate(
            current,
            deployment_gate,
            snapshot,
            migration,
            bad_runtime_capacity_contract,
            live_rollout,
            restored_smoke,
            rehearsal,
            [],
        )["passed"]
        is False,
        "production decision must block runtime capacity contract deployment substitution",
    )

    bad_rollback_capacity_owner = copy.deepcopy(rehearsal)
    bad_rollback_capacity_owner["capacity_contract"]["current_infrastructure_deployment_id"] = previous["deployment_id"]
    require(
        deployment_decision.evaluate(
            current,
            deployment_gate,
            snapshot,
            migration,
            restored_runtime,
            live_rollout,
            restored_smoke,
            bad_rollback_capacity_owner,
            [],
        )["passed"]
        is False,
        "production decision must block rollback evidence bound to another capacity deployment",
    )

    bad_rollback_capacity_preservation = copy.deepcopy(rehearsal)
    bad_rollback_capacity_preservation["capacity_contract"]["preserved_across_image_rollback"] = False
    require(
        deployment_decision.evaluate(
            current,
            deployment_gate,
            snapshot,
            migration,
            restored_runtime,
            live_rollout,
            restored_smoke,
            bad_rollback_capacity_preservation,
            [],
        )["passed"]
        is False,
        "production decision must block rollback without capacity preservation proof",
    )

    bad_rollout = copy.deepcopy(live_rollout)
    bad_rollout["canary_percent"] = 100
    require(
        deployment_decision.evaluate(
            current,
            deployment_gate,
            snapshot,
            migration,
            restored_runtime,
            bad_rollout,
            restored_smoke,
            rehearsal,
            [],
        )["passed"]
        is False,
        "100-percent canary evidence must block",
    )
    alarmed = copy.deepcopy(live_rollout)
    alarmed["alarms"][0]["state"] = "ALARM"
    require(
        deployment_decision.evaluate(
            current,
            deployment_gate,
            snapshot,
            migration,
            restored_runtime,
            alarmed,
            restored_smoke,
            rehearsal,
            [],
        )["passed"]
        is False,
        "ALARM state must block production decision",
    )
    failed_migration = copy.deepcopy(migration)
    failed_migration["passed"] = False
    failed_migration["exit_code"] = 1
    require(
        deployment_decision.evaluate(
            current,
            deployment_gate,
            snapshot,
            failed_migration,
            restored_runtime,
            live_rollout,
            restored_smoke,
            rehearsal,
            [],
        )["passed"]
        is False,
        "failed migration must block production decision",
    )
    incomplete_rollback = copy.deepcopy(rehearsal)
    incomplete_rollback["roll_forward_restored"] = False
    require(
        deployment_decision.evaluate(
            current,
            deployment_gate,
            snapshot,
            migration,
            restored_runtime,
            live_rollout,
            restored_smoke,
            incomplete_rollback,
            [],
        )["passed"]
        is False,
        "rollback without restored current RC must block",
    )

    identity_script = (ROOT / "scripts/capture-production-runtime-identity.sh").read_text()
    rollout_script = (ROOT / "scripts/capture-production-rollout-evidence.sh").read_text()
    deploy_workflow = (ROOT / ".github/workflows/deploy-production.yml").read_text()
    rollback_workflow = (ROOT / ".github/workflows/production-rollback-rehearsal.yml").read_text()
    freeze_workflow = (ROOT / ".github/workflows/freeze-production-evidence.yml").read_text()
    deployment_source = DEPLOYMENT_DECISION.read_text()
    rollback_source = ROLLBACK_DECISION.read_text()

    require("describe-task-definition" in identity_script, "runtime identity must inspect task definitions")
    require("expected exactly seven ECS services" in identity_script, "runtime identity must require seven services")
    require('IMAGE_KEY="worker-media"' in identity_script, "dispatcher must map to worker-media image identity")
    require("service_desired_counts" in identity_script, "runtime identity must read Terraform desired counts")
    require("expected_desired_count" in identity_script, "runtime identity must freeze expected desired count")
    require("capacity_matches" in identity_script, "runtime identity must freeze capacity match")
    require("capacity_contract_deployment_id" in identity_script, "runtime identity must freeze capacity deployment identity")
    require("capacity_contract_service_desired_counts" in identity_script, "runtime identity must freeze canonical capacity map")
    require("_capacity_row_valid" in deployment_source, "production decision must recompute runtime capacity validity")
    require("_validate_capacity_contract" in deployment_source, "production decision must validate runtime capacity contract")
    require("outbox-dispatcher" in deployment_source, "production decision must bind dispatcher identity")
    require("outbox-dispatcher" in rollback_source, "rollback decision must bind dispatcher identity")
    require("preserved_across_image_rollback" in rollback_source, "rollback decision must freeze capacity preservation semantics")
    require("current_infrastructure_deployment_id" in rollback_source, "rollback decision must bind current infrastructure identity")
    require("deploymentConfiguration" in rollout_script, "rollout evidence must read live ECS deployment config")
    require("alarms.rollback" in rollout_script, "rollout evidence must require alarm rollback")
    require("capture-production-runtime-identity.sh" in deploy_workflow, "deploy workflow must capture exact image identity")
    require("capture-production-rollout-evidence.sh" in deploy_workflow, "deploy workflow must capture live rollout config")
    require("environment: production" in rollback_workflow, "rollback rehearsal must use protected production environment")
    require("Verify previous six-runtime identity on current infrastructure capacity" in rollback_workflow, "rollback target must declare current capacity semantics")
    require('"$CURRENT_DEPLOYMENT_ID"' in rollback_workflow, "rollback runtime capture must bind current capacity deployment id")
    require("Best-effort restore current RC after failed rehearsal" in rollback_workflow, "failed rehearsal must attempt current-RC restoration")
    require("production-deployment-decision.py" in freeze_workflow, "evidence freeze must recompute NODE-72 decision")
    require("git push origin" in freeze_workflow, "validated evidence freeze must persist to repository")

    print(
        json.dumps(
            {
                "status": "PASS",
                "drills": {
                    "cross_account_rollback_blocked": True,
                    "unsafe_database_rollback_blocked": True,
                    "mutable_rollback_image_blocked": True,
                    "rollback_target_capacity_owner_swap_blocked": True,
                    "rollback_target_capacity_map_forgery_blocked": True,
                    "wrong_rollforward_image_blocked": True,
                    "dispatcher_rollforward_image_swap_blocked": True,
                    "dispatcher_rollforward_capacity_drift_blocked": True,
                    "rollforward_capacity_owner_swap_blocked": True,
                    "wrong_previous_smoke_version_blocked": True,
                    "dispatcher_production_image_key_swap_blocked": True,
                    "dispatcher_production_capacity_drift_blocked": True,
                    "production_capacity_owner_swap_blocked": True,
                    "rollback_capacity_owner_swap_blocked": True,
                    "rollback_capacity_preservation_false_blocked": True,
                    "canary_100_percent_blocked": True,
                    "alarm_state_blocked": True,
                    "failed_migration_blocked": True,
                    "rollback_without_rollforward_blocked": True,
                    "runtime_identity_source_bound": True,
                    "runtime_capacity_source_bound": True,
                    "runtime_capacity_contract_source_bound": True,
                    "live_canary_source_bound": True,
                    "protected_rehearsal_source_bound": True,
                    "frozen_evidence_source_bound": True,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

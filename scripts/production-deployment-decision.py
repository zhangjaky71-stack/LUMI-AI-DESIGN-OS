#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_IMAGE_KEYS = {
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
}
RUNTIME_SERVICE_IMAGE_KEY = {
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


class ProductionDecisionError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ProductionDecisionError(f"{path} must contain a JSON object")
    return payload


def repo_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ProductionDecisionError(f"evidence path escapes repository: {path}") from exc


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ProductionDecisionError(f"evidence file missing: {path}")
    return {"path": repo_path(path), "sha256": digest(path)}


def rc(payload: dict[str, Any], key: str = "release_candidate") -> tuple[Any, Any, Any]:
    item = payload.get(key)
    if not isinstance(item, dict):
        return None, None, None
    return item.get("git_sha"), item.get("version"), item.get("migration_head")


def check_passed(
    payload: dict[str, Any],
    *,
    label: str,
    blockers: list[str],
    deployment_id: str | None = None,
) -> None:
    if payload.get("schema_version") != 1:
        blockers.append(f"{label} schema_version must be 1")
    if payload.get("passed") is not True:
        blockers.append(f"{label} is not passed=true")
    if deployment_id is not None and payload.get("deployment_id") != deployment_id:
        blockers.append(f"{label} deployment_id mismatch")


def _expected_service_images(images: object, blockers: list[str]) -> dict[str, str]:
    if not isinstance(images, dict) or set(images) != RUNTIME_IMAGE_KEYS:
        blockers.append("deployment manifest must contain exactly six canonical runtime images")
        return {}
    return {
        service: str(images[image_key])
        for service, image_key in RUNTIME_SERVICE_IMAGE_KEY.items()
    }


def _capacity_row_valid(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    expected = item.get("expected_desired_count")
    desired = item.get("desired_count")
    return (
        isinstance(expected, int)
        and not isinstance(expected, bool)
        and expected > 0
        and isinstance(desired, int)
        and not isinstance(desired, bool)
        and desired == expected
        and item.get("capacity_matches") is True
    )


def _validate_capacity_contract(
    runtime: dict[str, Any],
    services: list[Any],
    *,
    expected_deployment_id: Any,
    blockers: list[str],
) -> dict[str, int]:
    contract = runtime.get("capacity_contract")
    if not isinstance(contract, dict):
        blockers.append("runtime identity capacity_contract missing")
        return {}

    valid = True
    if contract.get("schema_version") != 1:
        blockers.append("runtime identity capacity_contract schema_version must be 1")
        valid = False
    if contract.get("source") != CAPACITY_CONTRACT_SOURCE:
        blockers.append("runtime identity capacity_contract source mismatch")
        valid = False
    if contract.get("scope") != CAPACITY_CONTRACT_SCOPE:
        blockers.append("runtime identity capacity_contract scope mismatch")
        valid = False
    if contract.get("deployment_id") != expected_deployment_id:
        blockers.append("runtime identity capacity_contract deployment_id mismatch")
        valid = False

    counts = contract.get("service_desired_counts")
    if not isinstance(counts, dict) or set(counts) != set(RUNTIME_SERVICE_IMAGE_KEY):
        blockers.append("runtime identity capacity_contract must contain exactly seven service counts")
        return {}
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in counts.values()
    ):
        blockers.append("runtime identity capacity_contract counts must be positive integers")
        return {}
    row_counts = {
        item.get("service_name"): item.get("expected_desired_count")
        for item in services
        if isinstance(item, dict) and isinstance(item.get("service_name"), str)
    }
    if row_counts != counts:
        blockers.append("runtime identity capacity_contract does not equal per-service Terraform expectations")
        valid = False
    if not valid:
        return {}
    return {str(name): int(value) for name, value in counts.items()}


def evaluate(
    manifest: dict[str, Any],
    deployment_gate: dict[str, Any],
    snapshot: dict[str, Any],
    migration: dict[str, Any],
    runtime: dict[str, Any],
    rollout: dict[str, Any],
    smoke: dict[str, Any],
    rollback: dict[str, Any],
    refs: list[dict[str, str]],
) -> dict[str, Any]:
    blockers: list[str] = []
    deployment_id = manifest.get("deployment_id")
    manifest_rc = rc(manifest)
    if manifest.get("schema_version") != 1 or manifest.get("environment") != "production":
        blockers.append("deployment manifest is not schema-v1 production")
    if not isinstance(deployment_id, str) or not deployment_id:
        blockers.append("deployment manifest deployment_id missing")

    check_passed(deployment_gate, label="deployment-gate", blockers=blockers, deployment_id=deployment_id)
    if rc(deployment_gate) != manifest_rc:
        blockers.append("deployment-gate RC identity mismatch")

    check_passed(snapshot, label="predeploy-snapshot", blockers=blockers, deployment_id=deployment_id)
    if snapshot.get("status") != "available":
        blockers.append("predeploy snapshot is not available")

    check_passed(migration, label="migration", blockers=blockers, deployment_id=deployment_id)
    if migration.get("exit_code") != 0:
        blockers.append("migration exit_code is not zero")

    check_passed(runtime, label="runtime-identity", blockers=blockers, deployment_id=deployment_id)
    if rc(runtime) != manifest_rc:
        blockers.append("runtime identity RC mismatch")
    services = runtime.get("services")
    expected_service_images = _expected_service_images(manifest.get("images"), blockers)
    runtime_capacity: dict[str, int] = {}
    if not isinstance(services, list) or len(services) != len(RUNTIME_SERVICE_IMAGE_KEY):
        blockers.append("runtime identity must contain exactly seven services")
    else:
        observed_images = {
            item.get("service_name"): item.get("image")
            for item in services
            if isinstance(item, dict) and isinstance(item.get("service_name"), str)
        }
        observed_image_keys = {
            item.get("service_name"): item.get("image_key")
            for item in services
            if isinstance(item, dict) and isinstance(item.get("service_name"), str)
        }
        if observed_images != expected_service_images:
            blockers.append(
                "deployed seven-service runtime images do not match the accepted six-image mapping"
            )
        if observed_image_keys != RUNTIME_SERVICE_IMAGE_KEY:
            blockers.append("runtime identity service-to-image-key mapping is not canonical")
        if any(
            not isinstance(item, dict)
            or item.get("expected_image") != expected_service_images.get(item.get("service_name"))
            or item.get("image_matches") is not True
            or not _capacity_row_valid(item)
            or item.get("steady") is not True
            for item in services
        ):
            blockers.append(
                "runtime identity contains non-steady, image-mismatched, or Terraform-capacity-mismatched service"
            )
        runtime_capacity = _validate_capacity_contract(
            runtime,
            services,
            expected_deployment_id=deployment_id,
            blockers=blockers,
        )

    check_passed(rollout, label="rollout-evidence", blockers=blockers, deployment_id=deployment_id)
    if rc(rollout) != manifest_rc:
        blockers.append("rollout evidence RC mismatch")
    expected_rollout = manifest.get("rollout")
    if not isinstance(expected_rollout, dict):
        blockers.append("manifest rollout object missing")
    else:
        if rollout.get("strategy") != "CANARY":
            blockers.append("live public API deployment strategy is not CANARY")
        if rollout.get("canary_percent") != expected_rollout.get("public_api_canary_percent"):
            blockers.append("live canary percentage does not match manifest")
        if rollout.get("bake_time_minutes") != expected_rollout.get("public_api_canary_bake_minutes"):
            blockers.append("live canary bake time does not match manifest")
        if rollout.get("canary_bake_time_minutes") != expected_rollout.get("public_api_canary_bake_minutes"):
            blockers.append("live canary configuration bake time does not match manifest")
        if rollout.get("alarms_enabled") is not True or rollout.get("alarms_rollback") is not True:
            blockers.append("live canary alarms are not enabled with rollback")
        if not rollout.get("alternate_target_group_arn") or not rollout.get("production_listener_rule"):
            blockers.append("live canary blue/green routing evidence is incomplete")
        alarms = rollout.get("alarms")
        if not isinstance(alarms, list) or len(alarms) < 2:
            blockers.append("live canary alarm evidence must contain at least two alarms")
        elif any(not isinstance(item, dict) or item.get("state") == "ALARM" for item in alarms):
            blockers.append("live canary alarm evidence contains ALARM/invalid state")

    check_passed(smoke, label="production-smoke", blockers=blockers)
    candidate = manifest.get("release_candidate")
    edge = manifest.get("edge")
    results = smoke.get("results")
    if not isinstance(candidate, dict) or not isinstance(edge, dict):
        blockers.append("manifest RC/edge missing for smoke validation")
    else:
        if smoke.get("base_url") != f"https://{edge.get('domain')}":
            blockers.append("production smoke base_url mismatch")
        version = results.get("/version") if isinstance(results, dict) else None
        if not isinstance(version, dict) or version.get("version") != candidate.get("version"):
            blockers.append("production smoke version mismatch")

    if rollback.get("schema_version") != 1 or rollback.get("passed") is not True:
        blockers.append("rollback rehearsal is not passed=true")
    if rollback.get("current_deployment_id") != deployment_id:
        blockers.append("rollback rehearsal current deployment mismatch")
    if rc(rollback) != manifest_rc:
        blockers.append("rollback rehearsal RC identity mismatch")
    if rollback.get("rollback_executed") is not True:
        blockers.append("rollback rehearsal must prove rollback_executed=true")
    if rollback.get("roll_forward_restored") is not True:
        blockers.append("rollback rehearsal must prove roll_forward_restored=true")
    rollback_refs = rollback.get("evidence_refs")
    if not isinstance(rollback_refs, list) or not rollback_refs:
        blockers.append("rollback rehearsal must freeze its own evidence_refs")

    rollback_capacity = rollback.get("capacity_contract")
    if not isinstance(rollback_capacity, dict):
        blockers.append("rollback rehearsal capacity_contract missing")
    else:
        if rollback_capacity.get("schema_version") != 1:
            blockers.append("rollback rehearsal capacity_contract schema_version must be 1")
        if rollback_capacity.get("source") != CAPACITY_CONTRACT_SOURCE:
            blockers.append("rollback rehearsal capacity_contract source mismatch")
        if rollback_capacity.get("scope") != CAPACITY_CONTRACT_SCOPE:
            blockers.append("rollback rehearsal capacity_contract scope mismatch")
        if rollback_capacity.get("current_infrastructure_deployment_id") != deployment_id:
            blockers.append("rollback rehearsal capacity contract is not bound to current infrastructure")
        if rollback_capacity.get("preserved_across_image_rollback") is not True:
            blockers.append("rollback rehearsal did not prove capacity preservation across image rollback")
        if rollback_capacity.get("service_desired_counts") != runtime_capacity:
            blockers.append("rollback rehearsal capacity contract differs from deployed runtime capacity")

    release_candidate = manifest.get("release_candidate", {})
    payload: dict[str, Any] = {
        "schema_version": 1,
        "deployment_id": deployment_id,
        "release_candidate": release_candidate,
        "capacity_contract": {
            "schema_version": 1,
            "source": CAPACITY_CONTRACT_SOURCE,
            "scope": CAPACITY_CONTRACT_SCOPE,
            "deployment_id": deployment_id,
            "service_desired_counts": runtime_capacity,
        },
        "passed": not blockers,
        "evidence_refs": refs,
        "blockers": sorted(set(blockers)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["decision_id"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize NODE-72 production deployment decision")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--deployment-gate", required=True)
    parser.add_argument("--predeploy-snapshot", required=True)
    parser.add_argument("--migration", required=True)
    parser.add_argument("--runtime-identity", required=True)
    parser.add_argument("--rollout-evidence", required=True)
    parser.add_argument("--smoke", required=True)
    parser.add_argument("--rollback-rehearsal", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    paths = [
        Path(args.deployment_gate),
        Path(args.predeploy_snapshot),
        Path(args.migration),
        Path(args.runtime_identity),
        Path(args.rollout_evidence),
        Path(args.smoke),
        Path(args.rollback_rehearsal),
    ]
    try:
        result = evaluate(
            load_json(Path(args.manifest)),
            load_json(paths[0]),
            load_json(paths[1]),
            load_json(paths[2]),
            load_json(paths[3]),
            load_json(paths[4]),
            load_json(paths[5]),
            load_json(paths[6]),
            [freeze(path) for path in paths],
        )
    except (OSError, json.JSONDecodeError, ProductionDecisionError) as exc:
        raise SystemExit(f"production deployment decision invalid: {exc}") from exc

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if result["passed"] else "BLOCK", "decision_id": result["decision_id"]}, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

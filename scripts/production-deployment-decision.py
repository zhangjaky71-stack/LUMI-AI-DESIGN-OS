#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


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


def evaluate(
    manifest: dict[str, Any],
    deployment_gate: dict[str, Any],
    snapshot: dict[str, Any],
    migration: dict[str, Any],
    runtime: dict[str, Any],
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
    images = manifest.get("images")
    if not isinstance(services, list) or len(services) != 6 or not isinstance(images, dict):
        blockers.append("runtime identity must contain exactly six services")
    else:
        observed = {
            item.get("service_name"): item.get("image")
            for item in services
            if isinstance(item, dict) and isinstance(item.get("service_name"), str)
        }
        if observed != images:
            blockers.append("deployed runtime images do not exactly equal accepted deployment manifest")
        if any(
            not isinstance(item, dict)
            or item.get("image_matches") is not True
            or item.get("steady") is not True
            for item in services
        ):
            blockers.append("runtime identity contains non-steady or mismatched service")

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

    release_candidate = manifest.get("release_candidate", {})
    payload: dict[str, Any] = {
        "schema_version": 1,
        "deployment_id": deployment_id,
        "release_candidate": release_candidate,
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
    parser.add_argument("--smoke", required=True)
    parser.add_argument("--rollback-rehearsal", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    paths = [
        Path(args.deployment_gate),
        Path(args.predeploy_snapshot),
        Path(args.migration),
        Path(args.runtime_identity),
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

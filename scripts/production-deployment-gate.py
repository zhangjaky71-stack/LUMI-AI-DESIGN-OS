#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SHA40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
ACCOUNT_ID = re.compile(r"^[0-9]{12}$")
REGION = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+$")
ROLE_ARN = re.compile(r"^arn:aws(?:-[a-z]+)?:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$")
CERT_ARN = re.compile(r"^arn:aws(?:-[a-z]+)?:acm:[a-z0-9-]+:[0-9]{12}:certificate/[A-Za-z0-9-]+$")
READY_EXTERNAL = {"READY", "DISABLED_BY_RELEASE_SCOPE"}


class DeploymentGateError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DeploymentGateError(f"{path} must contain a JSON object")
    return payload


def present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "PENDING"


def require(condition: bool, message: str, blockers: list[str]) -> None:
    if not condition:
        blockers.append(message)


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    require(manifest.get("schema_version") == 1, "manifest schema_version must be 1", blockers)
    require(manifest.get("environment") == "production", "environment must be production", blockers)
    require(present(manifest.get("deployment_id")), "deployment_id is missing/PENDING", blockers)

    rc = manifest.get("release_candidate")
    if not isinstance(rc, dict):
        blockers.append("release_candidate object missing")
    else:
        sha = rc.get("git_sha")
        require(isinstance(sha, str) and bool(SHA40.fullmatch(sha.lower())), "release_candidate.git_sha must be exact SHA40", blockers)
        for key in ["version", "migration_head", "staging_acceptance_decision_id", "staging_acceptance_path"]:
            require(present(rc.get(key)), f"release_candidate.{key} is missing/PENDING", blockers)

    aws = manifest.get("aws")
    if not isinstance(aws, dict):
        blockers.append("aws object missing")
    else:
        require(isinstance(aws.get("account_id"), str) and bool(ACCOUNT_ID.fullmatch(aws["account_id"])), "aws.account_id must be 12 digits", blockers)
        require(isinstance(aws.get("region"), str) and bool(REGION.fullmatch(aws["region"])), "aws.region is invalid", blockers)
        require(isinstance(aws.get("production_role_arn"), str) and bool(ROLE_ARN.fullmatch(aws["production_role_arn"])), "aws.production_role_arn is invalid", blockers)

    edge = manifest.get("edge")
    if not isinstance(edge, dict):
        blockers.append("edge object missing")
    else:
        domain = edge.get("domain")
        require(present(domain) and "." in str(domain) and not str(domain).startswith("."), "edge.domain must be a concrete DNS name", blockers)
        require(isinstance(edge.get("certificate_arn"), str) and bool(CERT_ARN.fullmatch(edge["certificate_arn"])), "edge.certificate_arn is invalid", blockers)
        require(edge.get("waf_enabled") is True, "WAF must be enabled for production", blockers)
        require(edge.get("https_only") is True, "production edge must be HTTPS-only", blockers)

    required_images = {"api", "agent-runtime", "model-gateway", "tool-gateway", "worker-media", "sandbox-runtime"}
    images = manifest.get("images")
    if not isinstance(images, dict):
        blockers.append("images object missing")
    else:
        require(set(images) == required_images, f"images must pin exactly {sorted(required_images)}", blockers)
        for name in sorted(required_images):
            value = images.get(name)
            require(isinstance(value, str) and bool(DIGEST_IMAGE.fullmatch(value)), f"image {name} must use immutable @sha256 digest", blockers)

    rollout = manifest.get("rollout")
    expected_rollout = {
        "public_api_strategy": "ECS_CANARY",
        "public_api_canary_percent": 5,
        "public_api_canary_bake_minutes": 10,
        "public_api_alarm_rollback": True,
        "internal_service_strategy": "ROLLING_CIRCUIT_BREAKER",
    }
    if not isinstance(rollout, dict):
        blockers.append("rollout object missing")
    else:
        require(rollout == expected_rollout, "rollout must match the versioned NODE-72 ECS canary/rolling policy", blockers)

    limits = manifest.get("first_day_limits")
    required_limits = {
        "max_org_concurrent_agent_runs",
        "max_org_concurrent_generations",
        "max_org_concurrent_video_jobs",
        "daily_provider_spend_usd",
        "invite_rate_per_hour",
    }
    if not isinstance(limits, dict):
        blockers.append("first_day_limits object missing")
    else:
        require(set(limits) == required_limits, "first_day_limits fields do not match release contract", blockers)
        for key in sorted(required_limits):
            value = limits.get(key)
            require(isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < float(value) <= 100000, f"first_day_limits.{key} must be finite and positive", blockers)

    rollback = manifest.get("rollback")
    if not isinstance(rollback, dict):
        blockers.append("rollback object missing")
    else:
        require(present(rollback.get("previous_deployment_id")), "rollback.previous_deployment_id missing", blockers)
        require(present(rollback.get("previous_manifest_ref")), "rollback.previous_manifest_ref missing", blockers)
        require(rollback.get("database_backward_compatible") is True, "database rollback compatibility must be explicitly proven true", blockers)

    dependencies = manifest.get("external_dependencies")
    if not isinstance(dependencies, dict):
        blockers.append("external_dependencies object missing")
    else:
        expected = {"dns", "email_domain", "billing_provider", "model_provider", "support_on_call"}
        require(set(dependencies) == expected, "external_dependencies fields do not match release contract", blockers)
        for name in sorted(expected):
            require(dependencies.get(name) in READY_EXTERNAL, f"external dependency {name} must be READY or DISABLED_BY_RELEASE_SCOPE", blockers)

    approvals = manifest.get("approvals")
    if not isinstance(approvals, dict):
        blockers.append("approvals object missing")
    else:
        for key in ["staging_acceptance", "engineering", "security", "release_owner"]:
            require(approvals.get(key) == "APPROVED", f"approval {key} is not APPROVED", blockers)
    return blockers


def validate_acceptance(manifest: dict[str, Any], decision: dict[str, Any], acceptance_path: Path) -> list[str]:
    blockers: list[str] = []
    rc = manifest.get("release_candidate", {})
    if decision.get("schema_version") != 1:
        blockers.append("NODE-71 decision schema_version must be 1")
    if decision.get("passed") is not True:
        blockers.append("NODE-71 acceptance decision is not passed=true")
    if decision.get("decision_id") != rc.get("staging_acceptance_decision_id"):
        blockers.append("NODE-71 decision_id does not match deployment manifest")
    decision_rc = decision.get("release_candidate")
    if not isinstance(decision_rc, dict):
        blockers.append("NODE-71 decision release_candidate missing")
    else:
        if decision_rc.get("git_sha") != rc.get("git_sha"):
            blockers.append("NODE-71 accepted RC SHA does not match production deployment RC")
        if decision_rc.get("version") != rc.get("version"):
            blockers.append("NODE-71 accepted RC version does not match production deployment RC")
        if decision_rc.get("migration_head") != rc.get("migration_head"):
            blockers.append("NODE-71 accepted migration head does not match production deployment")
    configured_path = rc.get("staging_acceptance_path")
    if isinstance(configured_path, str):
        if Path(configured_path).as_posix() != acceptance_path.as_posix():
            blockers.append("staging_acceptance_path does not match the decision file evaluated by the gate")
    return blockers


def evaluate(manifest: dict[str, Any], decision: dict[str, Any], acceptance_path: Path) -> dict[str, Any]:
    blockers = validate_manifest(manifest)
    blockers.extend(validate_acceptance(manifest, decision, acceptance_path))
    payload = {
        "schema_version": 1,
        "deployment_id": manifest.get("deployment_id"),
        "release_candidate": manifest.get("release_candidate", {}),
        "aws": manifest.get("aws", {}),
        "images": manifest.get("images", {}),
        "rollout": manifest.get("rollout", {}),
        "staging_acceptance_decision_id": decision.get("decision_id"),
        "passed": not blockers,
        "blockers": sorted(set(blockers)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {"gate_id": hashlib.sha256(canonical.encode()).hexdigest()[:24], **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate LUMI production deployment against exact NODE-71 acceptance evidence")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--acceptance-decision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        manifest_path = Path(args.manifest)
        acceptance_path = Path(args.acceptance_decision)
        result = evaluate(load_json(manifest_path), load_json(acceptance_path), acceptance_path)
    except (DeploymentGateError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"production deployment gate invalid: {exc}") from exc
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if result["passed"] else "BLOCK", "gate_id": result["gate_id"]}, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

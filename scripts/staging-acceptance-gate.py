#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SHA40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
ALLOWED_STATUSES = {"PASS", "FAIL", "BLOCKED_EXTERNAL", "NOT_RUN"}
OPEN_STATES = {"OPEN", "ACKNOWLEDGED", "IN_PROGRESS"}
BLOCKING_SEVERITIES = {"critical", "high"}
REQUIRED_IMAGES = {
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
}
MODEL_GATEWAY_REQUIRED_SOURCE_PATHS = {
    "services/model-gateway",
    "services/model-gateway/src/lumi_model_gateway/openai_image_adapter.py",
    "services/asset-storage/src/lumi_asset_storage/s3.py",
    "apps/api/src/lumi_api/model_gateway_runtime.py",
    "apps/api/src/lumi_api/model_gateway_bootstrap.py",
    "apps/api/src/lumi_api/model_gateway_service.py",
    "apps/api/src/lumi_api/model_gateway_cli.py",
    "apps/api/src/lumi_api/model_paid_guard.py",
    "apps/api/src/lumi_api/provider_output_store.py",
    "apps/api/src/lumi_api/idempotency/gateway.py",
    "apps/api/src/lumi_api/costs/model_gateway_adapter.py",
}
WORKER_MEDIA_REQUIRED_SOURCE_PATHS = {
    "services/image-generation",
    "services/asset-storage/src/lumi_asset_storage/s3.py",
    "apps/worker-media/src/lumi_worker_media/app.py",
    "apps/worker-media/src/lumi_worker_media/job_runtime.py",
    "apps/worker-media/src/lumi_worker_media/image_gateway_runtime.py",
    "apps/worker-media/src/lumi_worker_media/image_generation_codec.py",
    "apps/worker-media/src/lumi_worker_media/image_generation_repository.py",
    "apps/worker-media/src/lumi_worker_media/image_generation_ports.py",
    "apps/worker-media/src/lumi_worker_media/image_generation_artifacts.py",
    "apps/worker-media/src/lumi_worker_media/image_generation_runtime.py",
}


class AcceptanceError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AcceptanceError(f"{path} must contain a JSON object")
    return raw


def non_pending_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "PENDING"


def validate_rc(evidence: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    rc = evidence.get("release_candidate")
    if not isinstance(rc, dict):
        return ["release_candidate object is missing"]
    git_sha = rc.get("git_sha")
    if not isinstance(git_sha, str) or not SHA40.fullmatch(git_sha.lower()):
        blockers.append("release_candidate.git_sha must be an exact 40-character SHA")
    for key in ["version", "environment_id", "container_image_set_ref", "migration_head"]:
        if not non_pending_string(rc.get(key)):
            blockers.append(f"release_candidate.{key} is missing/PENDING")
    base_url = rc.get("base_url")
    if not non_pending_string(base_url):
        blockers.append("release_candidate.base_url is missing/PENDING")
    else:
        parsed = urlsplit(str(base_url))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            blockers.append("release_candidate.base_url must be HTTPS without embedded credentials")
    return blockers


def validate_container_image_set(
    evidence: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    image_set = evidence.get("container_image_set")
    if not isinstance(image_set, dict):
        return {}, ["container_image_set object is missing"]

    images = image_set.get("images")
    provenance = image_set.get("provenance")
    if not isinstance(images, dict):
        blockers.append("container_image_set.images object is missing")
        images = {}
    if not isinstance(provenance, dict):
        blockers.append("container_image_set.provenance object is missing")
        provenance = {}

    if set(images) != REQUIRED_IMAGES:
        blockers.append(f"container image set must pin exactly {sorted(REQUIRED_IMAGES)}")
    if set(provenance) != REQUIRED_IMAGES:
        blockers.append(f"container image provenance must cover exactly {sorted(REQUIRED_IMAGES)}")

    rc = evidence.get("release_candidate")
    rc_sha = rc.get("git_sha") if isinstance(rc, dict) else None
    normalized_provenance: dict[str, Any] = {}
    for service in sorted(REQUIRED_IMAGES):
        image = images.get(service)
        if not isinstance(image, str) or not DIGEST_IMAGE.fullmatch(image):
            blockers.append(f"container image {service} must use immutable @sha256 digest")

        item = provenance.get(service)
        if not isinstance(item, dict):
            blockers.append(f"container image provenance {service} is missing")
            continue
        item_sha = item.get("git_sha")
        if item_sha != rc_sha or not isinstance(item_sha, str) or not SHA40.fullmatch(item_sha.lower()):
            blockers.append(f"container image provenance {service}.git_sha must equal accepted RC SHA")
        for key in ["build_recipe_ref", "entrypoint", "sbom_ref", "provenance_ref"]:
            if not non_pending_string(item.get(key)):
                blockers.append(f"container image provenance {service}.{key} is missing/PENDING")
        source_paths = item.get("source_paths")
        if not isinstance(source_paths, list) or not source_paths or not all(
            non_pending_string(value) for value in source_paths
        ):
            blockers.append(f"container image provenance {service}.source_paths must be a non-empty string array")
            source_paths = []
        normalized_provenance[service] = {
            "git_sha": item_sha,
            "build_recipe_ref": item.get("build_recipe_ref"),
            "entrypoint": item.get("entrypoint"),
            "sbom_ref": item.get("sbom_ref"),
            "provenance_ref": item.get("provenance_ref"),
            "source_paths": source_paths,
        }

    model_gateway = normalized_provenance.get("model-gateway", {})
    model_sources = set(model_gateway.get("source_paths") or [])
    missing_sources = sorted(MODEL_GATEWAY_REQUIRED_SOURCE_PATHS - model_sources)
    if missing_sources:
        blockers.append(
            "model-gateway image provenance is missing required hosted sources: "
            + ", ".join(missing_sources)
        )

    worker_media = normalized_provenance.get("worker-media", {})
    worker_sources = set(worker_media.get("source_paths") or [])
    missing_worker_sources = sorted(WORKER_MEDIA_REQUIRED_SOURCE_PATHS - worker_sources)
    if missing_worker_sources:
        blockers.append(
            "worker-media image provenance is missing required hosted image sources: "
            + ", ".join(missing_worker_sources)
        )

    normalized = {
        "images": {name: images.get(name) for name in sorted(REQUIRED_IMAGES)},
        "provenance": normalized_provenance,
    }
    return normalized, blockers


def validate_data_policy(evidence: dict[str, Any]) -> list[str]:
    policy = evidence.get("data_policy")
    if not isinstance(policy, dict):
        return ["data_policy object is missing"]
    blockers: list[str] = []
    if policy.get("production_customer_data_used") is not False:
        blockers.append("production customer data is forbidden in staging acceptance")
    if policy.get("test_data_only") is not True:
        blockers.append("data_policy.test_data_only must be true")
    if policy.get("staging_secrets_isolated") is not True:
        blockers.append("staging secrets must be isolated from production/local examples")
    return blockers


def validate_accounts(evidence: dict[str, Any]) -> list[str]:
    accounts = evidence.get("test_accounts")
    required = ["org_a_owner", "org_a_editor", "org_a_viewer", "org_b_owner", "platform_ops", "billing_test_org"]
    if not isinstance(accounts, dict):
        return ["test_accounts object is missing"]
    return [f"test account {key} is missing/PENDING" for key in required if not non_pending_string(accounts.get(key))]


def validate_parity(parity_contract: dict[str, Any], evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    required = parity_contract.get("required_checks")
    if not isinstance(required, list) or not required:
        raise AcceptanceError("environment parity contract has no required_checks")
    supplied = evidence.get("environment_parity")
    if not isinstance(supplied, dict):
        supplied = {}
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    for item in required:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise AcceptanceError("invalid parity contract item")
        check_id = item["id"]
        result = supplied.get(check_id)
        status = result.get("status") if isinstance(result, dict) else "NOT_RUN"
        evidence_ref = result.get("evidence_ref") if isinstance(result, dict) else None
        passed = status == "PASS" and non_pending_string(evidence_ref)
        checks.append({"id": check_id, "status": status, "passed": passed, "evidence_ref": evidence_ref})
        if not passed:
            blockers.append(f"environment parity {check_id} is not evidenced PASS")
    return checks, blockers


def validate_scenarios(manifest: dict[str, Any], evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise AcceptanceError("acceptance manifest has no scenarios")
    supplied = evidence.get("scenario_results")
    if not isinstance(supplied, dict):
        supplied = {}
    known_ids = {item.get("id") for item in scenarios if isinstance(item, dict)}
    extras = sorted(key for key in supplied if key not in known_ids)
    if extras:
        raise AcceptanceError(f"scenario_results contains unknown IDs: {extras}")

    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise AcceptanceError("scenario must be an object")
        scenario_id = scenario.get("id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise AcceptanceError("scenario id missing")
        priority = scenario.get("priority")
        severity = str(scenario.get("severity", "")).lower()
        external_allowed = scenario.get("external_dependency") is True
        result = supplied.get(scenario_id)
        if result is None:
            result = {}
        if not isinstance(result, dict):
            raise AcceptanceError(f"scenario result {scenario_id} must be an object")
        status = result.get("status", "NOT_RUN")
        if status not in ALLOWED_STATUSES:
            raise AcceptanceError(f"scenario {scenario_id} has invalid status {status!r}")
        actual = result.get("actual")
        evidence_ref = result.get("evidence_ref")
        owner = result.get("owner")
        external_reason = result.get("external_reason")
        evidence_complete = all(non_pending_string(value) for value in [actual, evidence_ref, owner])
        valid_external = status != "BLOCKED_EXTERNAL" or (
            external_allowed and non_pending_string(external_reason)
        )
        passed = status == "PASS" and evidence_complete
        blocking = priority == "P0" and not passed
        checks.append(
            {
                "id": scenario_id,
                "title": scenario.get("title"),
                "priority": priority,
                "severity": severity,
                "status": status,
                "passed": passed,
                "blocking": blocking,
                "evidence_ref": evidence_ref,
                "owner": owner,
            }
        )
        if status == "PASS" and not evidence_complete:
            blockers.append(f"scenario {scenario_id} says PASS but lacks actual/evidence_ref/owner")
        if status == "BLOCKED_EXTERNAL" and not valid_external:
            blockers.append(f"scenario {scenario_id} has invalid BLOCKED_EXTERNAL status")
        if blocking:
            blockers.append(f"P0 scenario {scenario_id} is not evidenced PASS")
    return checks, blockers


def validate_issues(evidence: dict[str, Any]) -> list[str]:
    issues = evidence.get("open_issues")
    if not isinstance(issues, list):
        return ["open_issues must be an array"]
    blockers: list[str] = []
    for issue in issues:
        if not isinstance(issue, dict):
            blockers.append("open issue entry must be an object")
            continue
        severity = str(issue.get("severity", "")).lower()
        status = str(issue.get("status", "")).upper()
        if severity in BLOCKING_SEVERITIES and status in OPEN_STATES:
            blockers.append(f"blocking issue {issue.get('id', 'UNKNOWN')} remains {status}")
    return blockers


def validate_approvals(evidence: dict[str, Any]) -> list[str]:
    approvals = evidence.get("approvals")
    required = ["engineering", "security", "product", "release_owner"]
    if not isinstance(approvals, dict):
        return ["approvals object is missing"]
    return [f"approval {key} is missing/PENDING" for key in required if not non_pending_string(approvals.get(key))]


def evaluate(manifest: dict[str, Any], parity_contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    blockers.extend(validate_rc(evidence))
    image_set, image_blockers = validate_container_image_set(evidence)
    blockers.extend(image_blockers)
    blockers.extend(validate_data_policy(evidence))
    blockers.extend(validate_accounts(evidence))
    parity_checks, parity_blockers = validate_parity(parity_contract, evidence)
    blockers.extend(parity_blockers)
    scenario_checks, scenario_blockers = validate_scenarios(manifest, evidence)
    blockers.extend(scenario_blockers)
    blockers.extend(validate_issues(evidence))
    blockers.extend(validate_approvals(evidence))

    p0 = [item for item in scenario_checks if item["priority"] == "P0"]
    p1 = [item for item in scenario_checks if item["priority"] == "P1"]
    passed = not blockers and all(item["passed"] for item in p0)
    canonical = {
        "schema_version": 1,
        "manifest_id": manifest.get("manifest_id"),
        "release_candidate": evidence.get("release_candidate"),
        "container_image_set": image_set,
        "summary": {
            "p0_total": len(p0),
            "p0_passed": sum(1 for item in p0 if item["passed"]),
            "p1_total": len(p1),
            "p1_passed": sum(1 for item in p1 if item["passed"]),
            "parity_total": len(parity_checks),
            "parity_passed": sum(1 for item in parity_checks if item["passed"]),
            "blocking_count": len(blockers),
        },
        "checks": scenario_checks,
        "parity_checks": parity_checks,
        "blockers": sorted(set(blockers)),
        "approvals": evidence.get("approvals"),
    }
    decision_payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    canonical["decision_id"] = hashlib.sha256(decision_payload.encode("utf-8")).hexdigest()
    canonical["passed"] = passed
    return canonical


def render_markdown(decision: dict[str, Any]) -> str:
    summary = decision.get("summary") if isinstance(decision.get("summary"), dict) else {}
    blockers = decision.get("blockers") if isinstance(decision.get("blockers"), list) else []
    status = "PASS" if decision.get("passed") is True else "BLOCKED"
    lines = [
        "# NODE-71 Staging Acceptance Decision",
        "",
        f"- Status: **{status}**",
        f"- Decision ID: `{decision.get('decision_id', 'UNKNOWN')}`",
        f"- P0: {summary.get('p0_passed', 0)}/{summary.get('p0_total', 0)} passed",
        f"- Parity: {summary.get('parity_passed', 0)}/{summary.get('parity_total', 0)} passed",
        f"- Blocking count: {summary.get('blocking_count', len(blockers))}",
        "",
        "## Blockers",
        "",
    ]
    if blockers:
        lines.extend(f"- {str(item)}" for item in blockers)
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate NODE-71 Production-like Staging acceptance evidence")
    parser.add_argument("--manifest", default="staging/acceptance/manifest-v1.json")
    parser.add_argument("--parity-contract", default="staging/acceptance/environment-parity-v1.json")
    parser.add_argument("--evidence", required=True)
    parser.add_argument(
        "--out",
        "--output",
        dest="output",
        default="artifacts/node-71-staging-decision.json",
    )
    parser.add_argument("--markdown")
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    parity = load_json(Path(args.parity_contract))
    evidence = load_json(Path(args.evidence))
    decision = evaluate(manifest, parity, evidence)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(decision, indent=2, sort_keys=True), encoding="utf-8")
    if args.markdown:
        markdown = Path(args.markdown)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown(decision), encoding="utf-8")
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0 if decision["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

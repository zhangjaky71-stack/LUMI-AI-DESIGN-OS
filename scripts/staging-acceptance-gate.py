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
    "apps/api/src/lumi_api/model_gateway_runtime.py",
    "apps/api/src/lumi_api/costs/model_gateway_adapter.py",
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
            external_allowed and non_pending_string(external_reason) and non_pending_string(evidence_ref) and non_pending_string(owner)
        )
        passed = status == "PASS" and evidence_complete
        if status == "PASS" and not evidence_complete:
            blockers.append(f"scenario {scenario_id} claims PASS without actual/evidence_ref/owner")
        if status == "BLOCKED_EXTERNAL" and not valid_external:
            blockers.append(f"scenario {scenario_id} has invalid BLOCKED_EXTERNAL evidence")
        if priority == "P0" and not passed:
            blockers.append(f"P0 scenario {scenario_id} is not evidenced PASS")
        if status == "FAIL" and severity in BLOCKING_SEVERITIES:
            blockers.append(f"{severity.upper()} scenario {scenario_id} failed")
        checks.append(
            {
                "id": scenario_id,
                "category": scenario.get("category"),
                "title": scenario.get("title"),
                "priority": priority,
                "severity": severity,
                "status": status,
                "passed": passed,
                "external_dependency": external_allowed,
                "evidence_ref": evidence_ref,
                "owner": owner,
            }
        )
    return checks, blockers


def validate_issues(evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    issues = evidence.get("open_issues", [])
    if not isinstance(issues, list):
        raise AcceptanceError("open_issues must be an array")
    blockers: list[str] = []
    normalized: list[dict[str, Any]] = []
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            raise AcceptanceError(f"open_issues[{index}] must be an object")
        severity = str(issue.get("severity", "")).lower()
        status = str(issue.get("status", "OPEN")).upper()
        issue_id = str(issue.get("id", f"issue-{index}"))
        normalized.append({"id": issue_id, "severity": severity, "status": status, "owner": issue.get("owner")})
        if severity in BLOCKING_SEVERITIES and status in OPEN_STATES:
            blockers.append(f"open {severity.upper()} issue {issue_id}")
    return normalized, blockers


def validate_approvals(evidence: dict[str, Any]) -> list[str]:
    approvals = evidence.get("approvals")
    required = ["engineering", "security", "product", "release_owner"]
    if not isinstance(approvals, dict):
        return ["approvals object is missing"]
    return [f"approval {key} is not APPROVED" for key in required if approvals.get(key) != "APPROVED"]


def markdown_report(decision: dict[str, Any]) -> str:
    lines = [
        "# Staging Release Candidate Acceptance",
        "",
        f"- Decision ID: `{decision['decision_id']}`",
        f"- Status: **{'PASS' if decision['passed'] else 'BLOCK'}**",
        f"- RC SHA: `{decision['release_candidate'].get('git_sha', 'UNKNOWN')}`",
        f"- P0 passed: {decision['summary']['p0_passed']}/{decision['summary']['p0_total']}",
        f"- Scenarios: PASS {decision['summary']['pass']} / FAIL {decision['summary']['fail']} / BLOCKED_EXTERNAL {decision['summary']['blocked_external']} / NOT_RUN {decision['summary']['not_run']}",
        "",
        "## Blockers",
        "",
    ]
    if decision["blockers"]:
        lines.extend(f"- {item}" for item in decision["blockers"])
    else:
        lines.append("- None")
    lines.extend(["", "## Scenario results", "", "| ID | Priority | Severity | Status | Evidence |", "|---|---|---|---|---|"])
    for item in decision["scenario_checks"]:
        lines.append(
            f"| {item['id']} | {item['priority']} | {item['severity']} | {item['status']} | {item.get('evidence_ref') or ''} |"
        )
    return "\n".join(lines) + "\n"


def evaluate(manifest: dict[str, Any], parity: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema_version") != 1 or evidence.get("schema_version") != 1 or parity.get("schema_version") != 1:
        raise AcceptanceError("all contracts must use schema_version 1")
    if evidence.get("manifest_id") != manifest.get("manifest_id"):
        raise AcceptanceError("evidence manifest_id does not match acceptance manifest")

    blockers = []
    blockers.extend(validate_rc(evidence))
    image_set, image_blockers = validate_container_image_set(evidence)
    blockers.extend(image_blockers)
    blockers.extend(validate_data_policy(evidence))
    blockers.extend(validate_accounts(evidence))
    parity_checks, parity_blockers = validate_parity(parity, evidence)
    blockers.extend(parity_blockers)
    scenario_checks, scenario_blockers = validate_scenarios(manifest, evidence)
    blockers.extend(scenario_blockers)
    issues, issue_blockers = validate_issues(evidence)
    blockers.extend(issue_blockers)
    blockers.extend(validate_approvals(evidence))

    counts = {status: sum(1 for item in scenario_checks if item["status"] == status) for status in ALLOWED_STATUSES}
    p0 = [item for item in scenario_checks if item["priority"] == "P0"]
    payload = {
        "schema_version": 1,
        "manifest_id": manifest.get("manifest_id"),
        "release_candidate": evidence.get("release_candidate", {}),
        "container_image_set": image_set,
        "passed": not blockers,
        "summary": {
            "pass": counts["PASS"],
            "fail": counts["FAIL"],
            "blocked_external": counts["BLOCKED_EXTERNAL"],
            "not_run": counts["NOT_RUN"],
            "p0_total": len(p0),
            "p0_passed": sum(1 for item in p0 if item["passed"]),
            "parity_total": len(parity_checks),
            "parity_passed": sum(1 for item in parity_checks if item["passed"]),
        },
        "blockers": sorted(set(blockers)),
        "parity_checks": parity_checks,
        "scenario_checks": scenario_checks,
        "open_issues": issues,
        "approvals": evidence.get("approvals", {}),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {"decision_id": hashlib.sha256(canonical.encode()).hexdigest()[:24], **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate LUMI staging release-candidate acceptance evidence")
    parser.add_argument("--manifest", default="staging/acceptance/manifest-v1.json")
    parser.add_argument("--parity", default="staging/acceptance/environment-parity-v1.json")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown")
    args = parser.parse_args()
    try:
        decision = evaluate(load_json(Path(args.manifest)), load_json(Path(args.parity)), load_json(Path(args.evidence)))
    except (AcceptanceError, json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"staging acceptance gate invalid: {exc}") from exc
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown:
        markdown = Path(args.markdown)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(markdown_report(decision), encoding="utf-8")
    print(json.dumps({"status": "PASS" if decision["passed"] else "BLOCK", "decision_id": decision["decision_id"]}, sort_keys=True))
    return 0 if decision["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

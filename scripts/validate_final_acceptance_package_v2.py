#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GOVERNANCE_POLICY_VALIDATOR = ROOT / "scripts" / "validate_release_governance_policy.py"
AUTHORIZATION_V2 = ROOT / "scripts" / "capture_release_authorization_v2.py"
APPROVAL_POLICY_FEASIBILITY = ROOT / "scripts" / "validate_release_approval_policy_feasibility_v2.py"
UPSTREAM = {"security", "recovery", "performance", "ai_regression", "staging_acceptance", "production_deployment"}
APPROVAL_KEYS = {"product", "engineering", "security", "operations", "release_owner"}
EXPECTED_KIND = "LUMI_FINAL_ACCEPTANCE_PACKAGE_V2"


class PackageV2Error(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PackageV2Error(f"{path} must contain a JSON object")
    return payload


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PackageV2Error(f"unable to import {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repo_file(raw: Any, *, prefixes: tuple[str, ...] | None = None) -> Path:
    if not isinstance(raw, str) or not raw or raw.upper() == "PENDING":
        raise PackageV2Error("frozen path missing/PENDING")
    path = (ROOT / raw).resolve()
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise PackageV2Error(f"path escapes repository: {raw}") from exc
    if prefixes is not None and not any(relative == prefix.rstrip("/") or relative.startswith(prefix) for prefix in prefixes):
        raise PackageV2Error(f"path outside allowed roots: {raw}")
    if not path.is_file():
        raise PackageV2Error(f"frozen file missing: {raw}")
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_ref(ref: Any, *, label: str, prefixes: tuple[str, ...] | None = None) -> Path:
    if not isinstance(ref, dict):
        raise PackageV2Error(f"{label} must be an object")
    path = repo_file(ref.get("path"), prefixes=prefixes)
    expected = ref.get("sha256")
    if not isinstance(expected, str) or not SHA256.fullmatch(expected.lower()) or digest(path) != expected.lower():
        raise PackageV2Error(f"{label} SHA-256 mismatch")
    return path


def rc(payload: dict[str, Any]) -> tuple[Any, Any, Any]:
    value = payload.get("release_candidate")
    if not isinstance(value, dict):
        return None, None, None
    return value.get("git_sha"), value.get("version"), value.get("migration_head")


def validate(release_path: Path) -> dict[str, Any]:
    release = load(release_path)
    release_id = release.get("release_id")
    expected_rc = rc(release)
    if release.get("schema_version") != 2 or release.get("kind") != EXPECTED_KIND:
        raise PackageV2Error("release package must be schema-v2 LUMI_FINAL_ACCEPTANCE_PACKAGE_V2")
    if not isinstance(release_id, str) or not release_id:
        raise PackageV2Error("release package release_id invalid")
    release_sha = expected_rc[0]
    if not isinstance(release_sha, str) or not SHA40.fullmatch(release_sha.lower()) or any(value is None or value == "PENDING" for value in expected_rc):
        raise PackageV2Error("release package Source RC identity incomplete")

    assembly = release.get("assembly")
    if not isinstance(assembly, dict) or assembly.get("schema_version") != 2:
        raise PackageV2Error("release package lacks canonical V2 assembly metadata")
    if assembly.get("assembler") != "scripts/final-acceptance-assembler-v2.py":
        raise PackageV2Error("release package was not produced by canonical V2 assembler")
    matrix_path = verify_ref(assembly.get("matrix"), label="assembly.matrix", prefixes=("final/acceptance/",))
    scenario_path = verify_ref(assembly.get("scenario_results"), label="assembly.scenario_results", prefixes=("reports/final-acceptance/",))
    if matrix_path.resolve() != (ROOT / "final/acceptance/manifest-v1.json").resolve():
        raise PackageV2Error("release package does not use canonical final acceptance matrix")

    governance_path = verify_ref(release.get("repository_governance_policy"), label="repository_governance_policy", prefixes=("final/acceptance/", "reports/final-acceptance/"))
    governance = load_module(GOVERNANCE_POLICY_VALIDATOR, "lumi_governance_policy_package_v2")
    try:
        governance.validate_policy(load(governance_path))
    except governance.GovernancePolicyError as exc:
        raise PackageV2Error(f"repository governance policy invalid: {exc}") from exc

    authorization_path = verify_ref(release.get("release_authorization_request"), label="release_authorization_request", prefixes=("reports/final-acceptance/",))
    authorization = load_module(AUTHORIZATION_V2, "lumi_authorization_package_v2")
    try:
        request, _policy_path, approval_policy = authorization.validate_request(load(authorization_path))
    except authorization.ReleaseAuthorizationV2Error as exc:
        raise PackageV2Error(f"release authorization request invalid: {exc}") from exc
    feasibility = load_module(APPROVAL_POLICY_FEASIBILITY, "lumi_approval_policy_feasibility_package_v2")
    try:
        feasibility_result = feasibility.validate_policy(approval_policy)
    except feasibility.ApprovalPolicyFeasibilityError as exc:
        raise PackageV2Error(f"release approval principal policy is not satisfiable: {exc}") from exc
    if request.get("release_id") != release_id:
        raise PackageV2Error("release authorization request release_id mismatch")
    source = request.get("source_release_candidate")
    request_rc = (source.get("git_sha"), source.get("version"), source.get("migration_head")) if isinstance(source, dict) else (None, None, None)
    if request_rc != expected_rc:
        raise PackageV2Error("release authorization request Source RC identity mismatch")
    if release.get("operational_handoff") != request.get("operational_handoff"):
        raise PackageV2Error("release operational handoff differs from authorization request")
    approvals = release.get("approvals")
    if not isinstance(approvals, dict) or set(approvals) != APPROVAL_KEYS:
        raise PackageV2Error(f"release approvals must contain exactly {sorted(APPROVAL_KEYS)}")
    if any(value != "PENDING" for value in approvals.values()):
        raise PackageV2Error("committed V2 release approvals must remain PENDING until live Final Decision")
    if "release_authorization" in release or "repository_governance" in release:
        raise PackageV2Error("committed V2 package must not contain head-bound live authorization/governance reports")

    production = release.get("production")
    if not isinstance(production, dict):
        raise PackageV2Error("production object missing")
    deployment_manifest = verify_ref({"path": production.get("deployment_manifest_path"), "sha256": production.get("deployment_manifest_sha256")}, label="production.deployment_manifest", prefixes=("reports/production-deployments/",))
    deployment = load(deployment_manifest)
    if deployment.get("deployment_id") != production.get("deployment_id") or rc(deployment) != expected_rc:
        raise PackageV2Error("production deployment manifest identity mismatch")

    upstream = release.get("upstream_gates")
    if not isinstance(upstream, dict) or set(upstream) != UPSTREAM:
        raise PackageV2Error(f"release upstream gate set must equal {sorted(UPSTREAM)}")
    upstream_decisions: dict[str, str] = {}
    for name in sorted(UPSTREAM):
        path = verify_ref(upstream[name], label=f"upstream.{name}", prefixes=("reports/",))
        decision = load(path)
        if decision.get("passed") is not True or not isinstance(decision.get("decision_id"), str) or not decision["decision_id"]:
            raise PackageV2Error(f"upstream {name} is not a concrete passed=true decision")
        if rc(decision) != expected_rc:
            raise PackageV2Error(f"upstream {name} Source RC identity mismatch")
        refs = decision.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise PackageV2Error(f"upstream {name} lacks frozen evidence_refs")
        for index, ref in enumerate(refs):
            verify_ref(ref, label=f"upstream.{name}.evidence_refs[{index}]")
        upstream_decisions[name] = str(decision["decision_id"])

    evidence_path = verify_ref(release.get("acceptance_evidence"), label="acceptance_evidence", prefixes=("reports/final-acceptance/",))
    evidence = load(evidence_path)
    if evidence.get("release_id") != release_id or rc(evidence) != expected_rc:
        raise PackageV2Error("acceptance evidence release/Source RC identity mismatch")
    assembly_inputs = evidence.get("assembly_inputs")
    if not isinstance(assembly_inputs, dict):
        raise PackageV2Error("acceptance evidence lacks assembly_inputs")
    scenario_input = verify_ref(assembly_inputs.get("scenario_results"), label="acceptance_evidence.scenario_results", prefixes=("reports/final-acceptance/",))
    if scenario_input.resolve() != scenario_path.resolve():
        raise PackageV2Error("acceptance evidence scenario-results source mismatch")
    blockers = release.get("release_blockers")
    if not isinstance(blockers, list) or blockers:
        raise PackageV2Error("committed V2 package must have zero release_blockers")

    return {
        "status": "PASS",
        "kind": EXPECTED_KIND,
        "release_id": release_id,
        "source_release_candidate": release.get("release_candidate"),
        "upstream_decisions": upstream_decisions,
        "governance_policy_sha256": digest(governance_path),
        "authorization_request_sha256": digest(authorization_path),
        "approval_policy_feasible": True,
        "approval_policy_distinct_candidate_count": feasibility_result["distinct_candidate_count"],
        "scenario_results_sha256": digest(scenario_path),
        "acceptance_evidence_sha256": digest(evidence_path),
        "approvals_state": "PENDING_LIVE_AUTHORIZATION",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate non-cyclic NODE-73 Final Acceptance package V2")
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    try:
        path = repo_file(args.release, prefixes=("reports/final-acceptance/",))
        result = validate(path)
    except (OSError, json.JSONDecodeError, PackageV2Error) as exc:
        raise SystemExit(f"final acceptance package V2 invalid: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

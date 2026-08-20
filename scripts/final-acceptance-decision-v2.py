#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_GATE = ROOT / "scripts" / "final-acceptance-gate.py"
PACKAGE_V2 = ROOT / "scripts" / "validate_final_acceptance_package_v2.py"
GOVERNANCE = ROOT / "scripts" / "capture_release_branch_protection.py"
GOVERNANCE_BINDER_V2 = ROOT / "scripts" / "validate_live_release_governance_v2.py"
DISPATCH_REGISTRY_LIVE = ROOT / "scripts" / "validate_live_default_branch_dispatch_registry.py"
DISPATCH_REGISTRY_POLICY = ROOT / "production" / "release-actions" / "default-branch-dispatch-registry-v1.json"
AUTHORIZATION_V2 = ROOT / "scripts" / "capture_release_authorization_v2.py"
IDENTITY_V2 = ROOT / "scripts" / "validate_finalization_identity_v2.py"
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
EXPECTED_REF = "refs/heads/release-closure-p0"


class FinalDecisionV2Error(RuntimeError):
    pass


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise FinalDecisionV2Error(f"unable to import {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise FinalDecisionV2Error(f"path escapes repository: {path}") from exc


def resolve_output(raw: str) -> Path:
    path = (ROOT / raw).resolve()
    allowed = (ROOT / "reports" / "final-acceptance").resolve()
    try:
        path.relative_to(allowed)
    except ValueError as exc:
        raise FinalDecisionV2Error("final decision output must stay below reports/final-acceptance/") from exc
    if path.name != "final-decision-v2.json":
        raise FinalDecisionV2Error("final decision output filename must be final-decision-v2.json")
    return path


def require_token(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise FinalDecisionV2Error(f"required live-control token is missing: {name}")
    return value


def require_execution_context() -> str:
    if os.environ.get("GITHUB_REPOSITORY") != EXPECTED_REPOSITORY:
        raise FinalDecisionV2Error("Final Decision repository identity mismatch")
    if os.environ.get("GITHUB_REF") != EXPECTED_REF:
        raise FinalDecisionV2Error("Final Decision must execute from refs/heads/release-closure-p0")
    evidence = os.environ.get("GITHUB_SHA", "")
    if len(evidence) != 40 or any(char not in "0123456789abcdefABCDEF" for char in evidence):
        raise FinalDecisionV2Error("GITHUB_SHA/Evidence Head must be exact SHA40")
    return evidence.lower()


def evaluate(*, matrix_path: Path, release_path: Path, evidence_path: Path, output_path: Path) -> dict[str, Any]:
    product_gate = load_module(PRODUCT_GATE, "lumi_final_product_gate_v2")
    package = load_module(PACKAGE_V2, "lumi_final_package_v2")
    governance = load_module(GOVERNANCE, "lumi_release_governance_capture_v2")
    governance_binder = load_module(GOVERNANCE_BINDER_V2, "lumi_release_governance_policy_binding_v2")
    dispatch_registry = load_module(DISPATCH_REGISTRY_LIVE, "lumi_live_default_branch_dispatch_registry_v2")
    authorization = load_module(AUTHORIZATION_V2, "lumi_release_authorization_live_v2")
    identity = load_module(IDENTITY_V2, "lumi_finalization_identity_v2_runtime")

    try:
        package_result = package.validate(release_path)
    except package.PackageV2Error as exc:
        raise FinalDecisionV2Error(f"canonical V2 final package invalid: {exc}") from exc
    if package_result.get("status") != "PASS":
        raise FinalDecisionV2Error("canonical V2 final package did not PASS")

    release = product_gate.load_json(release_path)
    evidence = product_gate.load_json(evidence_path)
    matrix = product_gate.load_json(matrix_path)
    release_id = release.get("release_id")
    rc = release.get("release_candidate")
    if not isinstance(release_id, str) or not release_id:
        raise FinalDecisionV2Error("release_id is missing")
    if not isinstance(rc, dict) or not isinstance(rc.get("git_sha"), str):
        raise FinalDecisionV2Error("Source RC identity is missing")
    source_rc_sha = rc["git_sha"].lower()
    evidence_head_sha = require_execution_context()

    governance_spec = release.get("repository_governance_policy")
    if not isinstance(governance_spec, dict) or not isinstance(governance_spec.get("path"), str):
        raise FinalDecisionV2Error("repository_governance_policy frozen path is missing")
    governance_policy_path = product_gate.canonical_repo_path(
        governance_spec["path"],
        allowed_prefixes=("final/acceptance/", "reports/final-acceptance/"),
    )
    governance_policy = product_gate.load_json(governance_policy_path)

    auth_spec = release.get("release_authorization_request")
    if not isinstance(auth_spec, dict) or not isinstance(auth_spec.get("path"), str):
        raise FinalDecisionV2Error("release_authorization_request frozen path is missing")
    request_path = product_gate.canonical_repo_path(
        auth_spec["path"],
        allowed_prefixes=("reports/final-acceptance/",),
    )

    runtime_dir = output_path.parent / "runtime-v2"
    governance_path = runtime_dir / "repository-governance-live.json"
    dispatch_registry_path = runtime_dir / "default-branch-dispatch-registry-live.json"
    authorization_path = runtime_dir / "release-authorization-live.json"

    governance_token = require_token("RELEASE_GOVERNANCE_TOKEN")
    governance_report = governance.capture(EXPECTED_REPOSITORY, token=governance_token)
    write_json(governance_path, governance_report)
    try:
        governance_result = governance_binder.validate_live_report(
            governance_report,
            governance_policy,
            expected_repository=EXPECTED_REPOSITORY,
            expected_evidence_head_sha=evidence_head_sha,
        )
    except governance_binder.LiveGovernanceV2Error as exc:
        raise FinalDecisionV2Error(f"live repository governance blocked: {exc}") from exc

    approval_token = require_token("RELEASE_APPROVAL_TOKEN")
    try:
        dispatch_registry_report = dispatch_registry.capture(EXPECTED_REPOSITORY, token=approval_token)
    except dispatch_registry.LiveDispatchRegistryError as exc:
        raise FinalDecisionV2Error(f"live default-branch dispatch registry blocked: {exc}") from exc
    write_json(dispatch_registry_path, dispatch_registry_report)

    try:
        authorization_report = authorization.capture(
            request_path,
            evidence_head_sha=evidence_head_sha,
            token=approval_token,
        )
        authorization_result = authorization.validate_authorization_report(
            authorization_report,
            expected_release_id=release_id,
            expected_source_rc=(rc.get("git_sha"), rc.get("version"), rc.get("migration_head")),
            expected_evidence_head_sha=evidence_head_sha,
        )
    except authorization.ReleaseAuthorizationV2Error as exc:
        raise FinalDecisionV2Error(f"live release authorization blocked: {exc}") from exc
    write_json(authorization_path, authorization_report)

    try:
        finalization_identity = identity.from_environment(
            source_rc_sha=source_rc_sha,
            pr_head_sha=authorization_report["pull_request"]["head_sha"],
            live_branch_head_sha=governance_result["release_head_sha"],
        )
    except identity.FinalizationIdentityError as exc:
        raise FinalDecisionV2Error(f"Source RC / Evidence Head identity blocked: {exc}") from exc

    product_release = copy.deepcopy(release)
    product_release["schema_version"] = 1
    product_release.pop("kind", None)
    product_release["approvals"] = dict(authorization_result["approval_statuses"])
    product_release["operational_handoff"] = dict(authorization_result["operational_handoff"])
    product_result = product_gate.evaluate(matrix, product_release, evidence, evidence_path)
    product_decision_id = product_result.pop("decision_id")

    live_controls = {
        "repository_governance": {
            "path": repo_relative(governance_path),
            "sha256": sha256(governance_path),
            "kind": governance_report.get("kind"),
            "status": governance_result.get("status"),
            "protection_profile": governance_result.get("protection_profile"),
            "evidence_head_sha": governance_result.get("release_head_sha"),
            "required_status_contexts": governance_result.get("required_status_contexts"),
            "branch_status_contexts": governance_result.get("branch_status_contexts"),
            "status_check_policy_bound": governance_result.get("status_check_policy_bound"),
        },
        "default_branch_dispatch_registry": {
            "path": repo_relative(dispatch_registry_path),
            "sha256": sha256(dispatch_registry_path),
            "kind": dispatch_registry_report.get("kind"),
            "status": dispatch_registry_report.get("status"),
            "default_branch": dispatch_registry_report.get("default_branch"),
            "default_branch_head_sha": dispatch_registry_report.get("default_branch_head_sha"),
            "workflow_count": dispatch_registry_report.get("workflow_count"),
            "all_default_branch_workflows_fail_closed": dispatch_registry_report.get(
                "all_default_branch_workflows_fail_closed"
            ),
            "dispatch_input_schemas_bound_to_evidence_head": dispatch_registry_report.get(
                "dispatch_input_schemas_bound_to_evidence_head"
            ),
        },
        "release_authorization": {
            "path": repo_relative(authorization_path),
            "sha256": sha256(authorization_path),
            "kind": authorization_report.get("kind"),
            "status": authorization_result.get("status"),
            "source_release_candidate": authorization_result.get("source_release_candidate"),
            "evidence_head_sha": authorization_result.get("evidence_head_sha"),
            "distinct_approver_count": authorization_result.get("distinct_approver_count"),
            "actors": authorization_result.get("actors"),
        },
    }
    execution_identity = {
        **finalization_identity,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "run_url": (
            f"https://github.com/{EXPECTED_REPOSITORY}/actions/runs/{os.environ.get('GITHUB_RUN_ID')}"
            if os.environ.get("GITHUB_RUN_ID")
            else None
        ),
    }
    payload = {
        **product_result,
        "schema_version": 2,
        "kind": "LUMI_FINAL_ACCEPTANCE_DECISION_V2",
        "release_candidate": release.get("release_candidate"),
        "source_rc_sha": source_rc_sha,
        "evidence_head_sha": evidence_head_sha,
        "source_rc_ancestor_of_evidence_head": finalization_identity["source_rc_ancestor_of_evidence_head"],
        "product_decision_id": product_decision_id,
        "canonical_inputs": {
            "release_manifest": {"path": repo_relative(release_path), "sha256": sha256(release_path)},
            "acceptance_evidence": {"path": repo_relative(evidence_path), "sha256": sha256(evidence_path)},
            "acceptance_matrix": {"path": repo_relative(matrix_path), "sha256": sha256(matrix_path)},
            "repository_governance_policy": {
                "path": repo_relative(governance_policy_path),
                "sha256": sha256(governance_policy_path),
            },
            "release_authorization_request": {
                "path": repo_relative(request_path),
                "sha256": sha256(request_path),
            },
            "default_branch_dispatch_registry_policy": {
                "path": repo_relative(DISPATCH_REGISTRY_POLICY),
                "sha256": sha256(DISPATCH_REGISTRY_POLICY),
            },
        },
        "execution_identity": execution_identity,
        "live_release_controls": live_controls,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    result = {"decision_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24], **payload}
    write_json(output_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate non-cyclic NODE-73 Final Acceptance V2")
    parser.add_argument("--matrix", default="final/acceptance/manifest-v1.json")
    parser.add_argument("--release", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    product_gate = load_module(PRODUCT_GATE, "lumi_final_product_gate_v2_paths")
    try:
        matrix_path = product_gate.canonical_repo_path(args.matrix, allowed_prefixes=("final/acceptance/",))
        release_path = product_gate.canonical_repo_path(args.release, allowed_prefixes=("reports/final-acceptance/",))
        evidence_path = product_gate.canonical_repo_path(args.evidence, allowed_prefixes=("reports/final-acceptance/",))
        output_path = resolve_output(args.output)
        result = evaluate(matrix_path=matrix_path, release_path=release_path, evidence_path=evidence_path, output_path=output_path)
    except (OSError, json.JSONDecodeError, FinalDecisionV2Error, product_gate.FinalAcceptanceError) as exc:
        raise SystemExit(f"final acceptance decision V2 blocked: {exc}") from exc
    print(
        json.dumps(
            {
                "accepted": result["accepted"],
                "decision_id": result["decision_id"],
                "product_decision_id": result["product_decision_id"],
                "source_rc_sha": result["source_rc_sha"],
                "evidence_head_sha": result["evidence_head_sha"],
                "headline": result["headline"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

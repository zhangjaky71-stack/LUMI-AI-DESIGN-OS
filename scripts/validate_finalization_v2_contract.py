#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODULES = {
    "governance": ROOT / "scripts/validate_release_governance_policy.py",
    "live_governance": ROOT / "scripts/validate_live_release_governance_v2.py",
    "governance_apply": ROOT / "scripts/apply_release_branch_protection.py",
    "dispatch_registry": ROOT / "scripts/validate_release_dispatch_registry_contract.py",
    "live_dispatch_registry": ROOT / "scripts/validate_live_default_branch_dispatch_registry.py",
    "authorization": ROOT / "scripts/capture_release_authorization_v2.py",
    "approval_feasibility": ROOT / "scripts/validate_release_approval_policy_feasibility_v2.py",
    "authorization_prep": ROOT / "scripts/prepare_release_authorization_request_v2.py",
    "identity": ROOT / "scripts/validate_finalization_identity_v2.py",
    "package_contract": ROOT / "scripts/validate_final_acceptance_v2_package_contract.py",
    "assembler_workflow_contract": ROOT / "scripts/validate_final_acceptance_assembler_workflow_v2.py",
    "permissions": ROOT / "scripts/validate_release_workflow_permissions.py",
    "no_v1_bypass": ROOT / "scripts/validate_no_v1_finalization_workflow_bypass.py",
}
DECISION_V2 = ROOT / "scripts/final-acceptance-decision-v2.py"
LIVE_DISPATCH_REGISTRY = ROOT / "scripts/validate_live_default_branch_dispatch_registry.py"
PACKAGE_V2 = ROOT / "scripts/validate_final_acceptance_package_v2.py"
ASSEMBLER_V2 = ROOT / "scripts/final-acceptance-assembler-v2.py"
FINAL_WORKFLOW = ROOT / ".github/workflows/final-acceptance-gate.yml"
GOVERNANCE_WORKFLOW = ROOT / ".github/workflows/configure-release-branch-protection.yml"
RELEASE_TEMPLATE = ROOT / "final/acceptance/release-manifest-v2-template.json"
POLICY_TEMPLATE = ROOT / "final/acceptance/release-approval-policy-v2-template.json"
REQUEST_TEMPLATE = ROOT / "final/acceptance/release-authorization-request-v2-template.json"
GOVERNANCE_TEMPLATE = ROOT / "final/acceptance/repository-governance-policy-template.json"
CANONICAL_FINAL_CHECK = "node73-final-contract-gate"


class FinalizationV2ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalizationV2ContractError(message)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise FinalizationV2ContractError(f"unable to import {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def markers(path: Path, required: tuple[str, ...]) -> None:
    source = path.read_text(encoding="utf-8")
    for marker in required:
        require(marker in source, f"{path.relative_to(ROOT)} missing V2 marker: {marker}")


def run_self_tests(modules: dict[str, ModuleType]) -> None:
    expected = {
        "governance": ("negative_drills", 12),
        "live_governance": ("negative_drills", 7),
        "dispatch_registry": ("negative_drills", 5),
        "live_dispatch_registry": ("negative_drills", 7),
        "authorization": ("negative_drills", 6),
        "approval_feasibility": ("negative_drills", 5),
        "authorization_prep": ("negative_drills", 1),
        "identity": ("negative_drills", 7),
    }
    results: dict[str, dict[str, Any]] = {}
    for name, (field, count) in expected.items():
        result: dict[str, Any] = modules[name].self_test()
        results[name] = result
        require(result.get("status") == "PASS", f"{name} V2 self-test did not PASS")
        require(result.get(field) == count, f"{name} V2 self-test count drift")

    governance_apply: dict[str, Any] = modules["governance_apply"].self_test()
    require(governance_apply.get("status") == "PASS", "branch-protection applicator self-test did not PASS")
    require(governance_apply.get("preflight_guard") == "EVIDENCE_HEAD_EXACT", "branch-protection Evidence Head guard drift")
    require(governance_apply.get("evidence_head_lock") == "READ_ONLY", "branch-protection Evidence Head lock drift")
    require(governance_apply.get("evidence_head_first") is True, "branch-protection must lock Evidence Head before base branch")
    require(
        modules["approval_feasibility"].EXPECTED_PR_AUTHOR
        in results["approval_feasibility"]["clean"]["excluded_logins"],
        "approval feasibility must model PR #135 author exclusion",
    )
    require(modules["dispatch_registry"].main() == 0, "static release dispatch registry contract did not PASS")
    require(modules["package_contract"].main() == 0, "V2 assembler/package execution contract did not PASS")
    require(modules["assembler_workflow_contract"].main() == 0, "V2 assembler workflow contract did not PASS")
    require(modules["permissions"].main() == 0, "release workflow permission contract did not PASS")
    require(modules["no_v1_bypass"].main() == 0, "V1 finalization workflow bypass contract did not PASS")


def validate_templates(modules: dict[str, ModuleType]) -> None:
    release = json.loads(RELEASE_TEMPLATE.read_text(encoding="utf-8"))
    require(release.get("schema_version") == 2, "release manifest template schema must be V2")
    require(release.get("kind") == "LUMI_FINAL_ACCEPTANCE_PACKAGE_V2", "release manifest V2 kind mismatch")
    require(all(value == "PENDING" for value in release.get("approvals", {}).values()), "committed release approvals must remain PENDING")
    require("release_authorization" not in release and "repository_governance" not in release, "release template must not commit live reports")

    approval = json.loads(POLICY_TEMPLATE.read_text(encoding="utf-8"))
    require(approval.get("schema_version") == 2, "approval policy template schema must be V2")
    require(approval.get("require_exact_evidence_head_review_commit") is True, "approval reviews must bind Evidence Head")
    require("require_exact_rc_review_commit" not in approval, "approval policy must not bind reviews to Source RC")
    for role in modules["authorization"].ROLES:
        require(approval["roles"][role]["allowed_logins"] == ["PENDING"], f"approval role {role} must remain fail-closed until real principals are configured")

    request = json.loads(REQUEST_TEMPLATE.read_text(encoding="utf-8"))
    require(request.get("schema_version") == 2, "authorization request template schema must be V2")
    require("source_release_candidate" in request and "evidence_head_sha" not in request, "pre-final request must freeze Source RC but not Evidence Head")

    governance = json.loads(GOVERNANCE_TEMPLATE.read_text(encoding="utf-8"))
    normalized = modules["governance"].validate_policy(governance)
    checks = normalized["required_status_checks"]
    require(checks["required_contexts"] == [CANONICAL_FINAL_CHECK], "governance policy canonical required check drift")
    require(checks["strict"] is True and checks["allow_additional_contexts"] is True, "governance status-check policy drift")
    require(normalized["require_evidence_head_locked"] is True, "governance policy must lock Evidence Head")
    require(
        normalized["require_non_evidence_release_branches_unlocked"] is True,
        "governance policy must keep merge-target release branch unlocked",
    )


def validate_canonical_sources() -> None:
    markers(ASSEMBLER_V2, (
        '"kind": "LUMI_FINAL_ACCEPTANCE_PACKAGE_V2"',
        'approvals = {key: "PENDING" for key in APPROVAL_KEYS}',
        '"repository_governance_policy": governance_policy',
        '"release_authorization_request": authorization_request',
    ))
    assembler = ASSEMBLER_V2.read_text(encoding="utf-8")
    require('"release_authorization":' not in assembler, "V2 assembler must not freeze live authorization")
    require('"repository_governance":' not in assembler, "V2 assembler must not freeze live governance")

    markers(PACKAGE_V2, (
        'APPROVAL_POLICY_FEASIBILITY = ROOT / "scripts" / "validate_release_approval_policy_feasibility_v2.py"',
        'feasibility.validate_policy(approval_policy)',
        '"approval_policy_feasible": True',
        '"approvals_state": "PENDING_LIVE_AUTHORIZATION"',
    ))

    markers(LIVE_DISPATCH_REGISTRY, (
        'main_head_start = _branch_head(repository, EXPECTED_DEFAULT_BRANCH, token=token)',
        'blob_sha, stub_text = _contents(repository, path, main_head_start, token=token)',
        'main_head_end = _branch_head(repository, EXPECTED_DEFAULT_BRANCH, token=token)',
        'validate_stable_snapshot(main_head_start, main_head_end)',
        '"default_branch_head_stable_during_capture": True',
        '"workflow_blobs_bound_to_exact_default_branch_head": True',
    ))

    markers(DECISION_V2, (
        'GOVERNANCE_BINDER_V2 = ROOT / "scripts" / "validate_live_release_governance_v2.py"',
        'DISPATCH_REGISTRY_LIVE = ROOT / "scripts" / "validate_live_default_branch_dispatch_registry.py"',
        'DISPATCH_REGISTRY_POLICY = ROOT / "production" / "release-actions" / "default-branch-dispatch-registry-v1.json"',
        'governance_binder.validate_live_report(',
        'dispatch_registry.capture(EXPECTED_REPOSITORY, token=approval_token)',
        '"default_branch_dispatch_registry": {',
        '"default_branch_dispatch_registry_policy": {',
        'expected_evidence_head_sha=evidence_head_sha',
        'authorization.capture(',
        'evidence_head_sha=evidence_head_sha',
        'identity.from_environment(',
        'product_release["approvals"] = dict(authorization_result["approval_statuses"])',
        '"repository_governance_policy": {',
        '"release_authorization_request": {',
        '"evidence_head_locked": governance_result.get("evidence_head_locked")',
        '"evidence_head_lock_policy_bound": governance_result.get("evidence_head_lock_policy_bound")',
        '"status_check_policy_bound": governance_result.get("status_check_policy_bound")',
        '"kind": "LUMI_FINAL_ACCEPTANCE_DECISION_V2"',
    ))

    final = FINAL_WORKFLOW.read_text(encoding="utf-8")
    require("needs: [source-contract, canonical-lock-gate, contract-gate]" in final, "Final Decision must wait for canonical final check")
    require("needs.contract-gate.result == 'success'" in final, "Final Decision must require canonical final check success")
    require(final.count('ref: ${{ github.sha }}') == 3, "all Final Acceptance code-consuming jobs must checkout exact github.sha")
    require(final.count('persist-credentials: false') == 3, "Final Acceptance checkouts must not persist credentials")
    require(final.count(f"name: {CANONICAL_FINAL_CHECK}") == 1, "canonical final check display name must be unique")
    require("scripts/final-acceptance-decision-v2.py" in final, "Final workflow must use V2 outer decision")
    require("scripts/final-acceptance-decision.py" not in final, "Final workflow must not invoke V1 outer decision")

    final_decision_start = final.find("  final-decision:\n")
    contract_gate_start = final.find("  contract-gate:\n", final_decision_start + 1)
    require(final_decision_start >= 0 and contract_gate_start > final_decision_start, "Final workflow final-decision job boundary is invalid")
    final_decision_job = final[final_decision_start:contract_gate_start]
    governance_secret = "${{ secrets.RELEASE_GOVERNANCE_TOKEN }}"
    require("environment: production" in final_decision_job, "Administration-read Final Decision must remain production-environment protected")
    require(governance_secret in final_decision_job, "Final Decision is missing Administration-read governance secret")
    require(final.count(governance_secret) == 1, "Administration-read governance secret must be injected exactly once")
    require(
        "RELEASE_GOVERNANCE_TOKEN:" not in final[:final_decision_start] + final[contract_gate_start:],
        "Administration-read governance token must not escape final-decision job",
    )

    governance_workflow = GOVERNANCE_WORKFLOW.read_text(encoding="utf-8")
    preflight_start = governance_workflow.find("  pr-preflight:\n")
    apply_start = governance_workflow.find("  apply-protection:\n")
    require(preflight_start >= 0 and apply_start > preflight_start, "governance workflow must separate PR preflight from privileged mutation")
    preflight = governance_workflow[preflight_start:apply_start]
    mutation = governance_workflow[apply_start:]
    require("RELEASE_GOVERNANCE_ADMIN_TOKEN" not in preflight, "PR-controlled governance preflight must never receive Administration-write secret")
    require("environment: production" not in preflight, "PR-controlled governance preflight must remain outside secret environment")
    require("node73-protection-preflight" in preflight, "PR governance event must remain explicitly preflight-only")
    require("github.event_name == 'workflow_dispatch'" in mutation, "privileged governance mutation must be workflow_dispatch-only")
    require("github.event_name == 'pull_request'" not in mutation, "privileged governance mutation must reject pull_request events")
    require("environment: production" in mutation, "privileged governance mutation must remain production-environment protected")
    require(mutation.count("${{ secrets.RELEASE_GOVERNANCE_ADMIN_TOKEN }}") == 1, "Administration-write secret must be injected once in mutation job")


def main() -> int:
    modules = {name: load_module(path, f"lumi_node73_v2_{name}") for name, path in MODULES.items()}
    run_self_tests(modules)
    validate_templates(modules)
    validate_canonical_sources()
    print("NODE-73 Finalization Identity V2 source contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FinalizationV2ContractError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"finalization V2 source contract failed: {exc}") from exc

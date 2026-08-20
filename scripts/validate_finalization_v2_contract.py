#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_POLICY = ROOT / "scripts" / "validate_release_governance_policy.py"
AUTH_V2 = ROOT / "scripts" / "capture_release_authorization_v2.py"
IDENTITY_V2 = ROOT / "scripts" / "validate_finalization_identity_v2.py"
ASSEMBLER_V2 = ROOT / "scripts" / "final-acceptance-assembler-v2.py"
PACKAGE_V2 = ROOT / "scripts" / "validate_final_acceptance_package_v2.py"
PACKAGE_CONTRACT = ROOT / "scripts" / "validate_final_acceptance_v2_package_contract.py"
ASSEMBLER_WORKFLOW_CONTRACT = ROOT / "scripts" / "validate_final_acceptance_assembler_workflow_v2.py"
DECISION_V2 = ROOT / "scripts" / "final-acceptance-decision-v2.py"
FINAL_WORKFLOW = ROOT / ".github" / "workflows" / "final-acceptance-gate.yml"
RELEASE_TEMPLATE = ROOT / "final" / "acceptance" / "release-manifest-v2-template.json"
POLICY_TEMPLATE = ROOT / "final" / "acceptance" / "release-approval-policy-v2-template.json"
REQUEST_TEMPLATE = ROOT / "final" / "acceptance" / "release-authorization-request-v2-template.json"
GOVERNANCE_TEMPLATE = ROOT / "final" / "acceptance" / "repository-governance-policy-template.json"


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


def require_markers(path: Path, markers: tuple[str, ...]) -> None:
    text = path.read_text(encoding="utf-8")
    for marker in markers:
        require(marker in text, f"{path.relative_to(ROOT)} missing V2 marker: {marker}")


def main() -> int:
    governance = load_module(GOVERNANCE_POLICY, "lumi_governance_policy_contract_v2")
    auth = load_module(AUTH_V2, "lumi_authorization_contract_v2")
    identity = load_module(IDENTITY_V2, "lumi_identity_contract_v2")
    package_contract = load_module(PACKAGE_CONTRACT, "lumi_package_contract_v2")
    assembler_workflow_contract = load_module(
        ASSEMBLER_WORKFLOW_CONTRACT,
        "lumi_assembler_workflow_contract_v2",
    )
    governance_test: dict[str, Any] = governance.self_test()
    auth_test: dict[str, Any] = auth.self_test()
    identity_test: dict[str, Any] = identity.self_test()
    require(governance_test.get("status") == "PASS" and governance_test.get("negative_drills") == 6, "governance policy V2 self-test drift")
    require(auth_test.get("status") == "PASS" and auth_test.get("negative_drills") == 6, "authorization V2 self-test drift")
    require(identity_test.get("status") == "PASS" and identity_test.get("negative_drills") == 7, "finalization identity V2 self-test drift")
    require(package_contract.main() == 0, "V2 assembler/package execution contract did not PASS")
    require(assembler_workflow_contract.main() == 0, "V2 assembler workflow contract did not PASS")

    release_template = json.loads(RELEASE_TEMPLATE.read_text(encoding="utf-8"))
    require(release_template.get("schema_version") == 2 and release_template.get("kind") == "LUMI_FINAL_ACCEPTANCE_PACKAGE_V2", "release manifest V2 template mismatch")
    require(release_template.get("repository_governance_policy") == {"path": "PENDING", "sha256": "PENDING"}, "release template must freeze governance policy")
    require(release_template.get("release_authorization_request") == {"path": "PENDING", "sha256": "PENDING"}, "release template must freeze authorization request")
    require(all(value == "PENDING" for value in release_template.get("approvals", {}).values()), "release template approvals must remain PENDING")
    require("release_authorization" not in release_template and "repository_governance" not in release_template, "release template must not contain live reports")

    policy = json.loads(POLICY_TEMPLATE.read_text(encoding="utf-8"))
    require(policy.get("kind") == auth.POLICY_KIND and policy.get("schema_version") == 2, "approval policy V2 template mismatch")
    require(policy.get("require_exact_evidence_head_review_commit") is True, "approval policy must bind reviews to Evidence Head")
    require("require_exact_rc_review_commit" not in policy, "approval policy V2 must not bind reviews to Source RC")
    for role in auth.ROLES:
        require(policy["roles"][role]["allowed_logins"] == ["PENDING"], f"approval policy role {role} must remain fail-closed until configured")

    request = json.loads(REQUEST_TEMPLATE.read_text(encoding="utf-8"))
    require(request.get("kind") == auth.REQUEST_KIND and request.get("schema_version") == 2, "authorization request V2 template mismatch")
    require("source_release_candidate" in request and "evidence_head_sha" not in request, "authorization request must freeze Source RC but not Evidence Head")
    governance_template = json.loads(GOVERNANCE_TEMPLATE.read_text(encoding="utf-8"))
    require(governance_template.get("kind") == governance.KIND, "repository governance policy template kind mismatch")
    require(governance_template.get("require_live_reverification") is True, "repository governance policy must require live reverification")

    require_markers(ASSEMBLER_V2, (
        'parser.add_argument("--governance-policy", required=True)',
        'parser.add_argument("--authorization-request", required=True)',
        '"repository_governance_policy": governance_policy',
        '"release_authorization_request": authorization_request',
        'approvals = {key: "PENDING" for key in APPROVAL_KEYS}',
        '"kind": "LUMI_FINAL_ACCEPTANCE_PACKAGE_V2"',
        '"assembler": "scripts/final-acceptance-assembler-v2.py"',
    ))
    assembler_text = ASSEMBLER_V2.read_text(encoding="utf-8")
    require('"release_authorization":' not in assembler_text, "V2 assembler must not freeze a live authorization report")
    require('"repository_governance":' not in assembler_text, "V2 assembler must not freeze a live governance report")

    require_markers(PACKAGE_V2, (
        'EXPECTED_KIND = "LUMI_FINAL_ACCEPTANCE_PACKAGE_V2"',
        'release.get("repository_governance_policy")',
        'release.get("release_authorization_request")',
        'value != "PENDING"',
        '"committed V2 package must not contain head-bound live authorization/governance reports"',
        '"approvals_state": "PENDING_LIVE_AUTHORIZATION"',
    ))

    require_markers(AUTH_V2, (
        'AUTHORIZATION_KIND = "LUMI_RELEASE_AUTHORIZATION_V2"',
        '"source_release_candidate"',
        '"evidence_head_sha"',
        'review.get("commit_id") != evidence',
        'head.get("sha") == evidence',
        'expected_evidence_head_sha',
    ))

    require_markers(DECISION_V2, (
        'PACKAGE_V2 = ROOT / "scripts" / "validate_final_acceptance_package_v2.py"',
        'evidence_head_sha = require_execution_context()',
        'governance.capture(EXPECTED_REPOSITORY',
        'expected_release_sha=evidence_head_sha',
        'authorization.capture(',
        'evidence_head_sha=evidence_head_sha',
        'identity.from_environment(',
        'source_rc_sha=source_rc_sha',
        'product_release["approvals"] = dict(authorization_result["approval_statuses"])',
        '"source_rc_sha": source_rc_sha',
        '"evidence_head_sha": evidence_head_sha',
        '"source_rc_ancestor_of_evidence_head"',
        '"kind": "LUMI_FINAL_ACCEPTANCE_DECISION_V2"',
    ))

    require_markers(FINAL_WORKFLOW, (
        "needs: [source-contract, canonical-lock-gate]",
        "needs.source-contract.result == 'success'",
        "needs.canonical-lock-gate.result == 'success'",
        "github.ref == 'refs/heads/release-closure-p0'",
        'ref: ${{ github.sha }}',
        'fetch-depth: 0',
        "release.name != 'release-manifest-v2.json'",
        "output = release.parent / 'final-decision-v2.json'",
        'python3 scripts/validate_final_acceptance_package_v2.py --release "$FINAL_RELEASE"',
        'python3 scripts/final-acceptance-decision-v2.py',
        'name: final-acceptance-v2-${{ github.run_id }}',
    ))
    workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")
    final_start = workflow.find("  final-decision:\n")
    final_end = workflow.find("  contract-gate:\n", final_start)
    require(final_start >= 0 and final_end > final_start, "Final Acceptance final-decision job block missing")
    final_block = workflow[final_start:final_end]
    require("scripts/final-acceptance-decision.py" not in final_block, "canonical final-decision job must not invoke V1 decision")
    require("scripts/validate_final_acceptance_package.py" not in final_block, "canonical final-decision job must not invoke V1 package validator")
    require("release-manifest.json" not in final_block, "canonical final-decision job must not accept V1 release manifest filename")

    print("NODE-73 Finalization Identity V2 source contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FinalizationV2ContractError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"finalization V2 source contract failed: {exc}") from exc

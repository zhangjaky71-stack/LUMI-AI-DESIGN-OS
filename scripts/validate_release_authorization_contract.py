#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "scripts" / "capture_release_authorization.py"
POLICY_TEMPLATE = ROOT / "final" / "acceptance" / "release-approval-policy-template.json"
REQUEST_TEMPLATE = ROOT / "final" / "acceptance" / "release-authorization-request-template.json"
AUTH_TEMPLATE = ROOT / "final" / "acceptance" / "release-authorization-template.json"
ASSEMBLER = ROOT / "scripts" / "final-acceptance-assembler.py"
PACKAGE_VALIDATOR = ROOT / "scripts" / "validate_final_acceptance_package.py"
ASSEMBLER_CONTRACT = ROOT / "scripts" / "validate_final_acceptance_assembler_contract.py"
FINAL_WORKFLOW = ROOT / ".github" / "workflows" / "final-acceptance-gate.yml"


class AuthorizationContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorizationContractError(message)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AuthorizationContractError(f"unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_markers(path: Path, markers: tuple[str, ...]) -> None:
    text = path.read_text(encoding="utf-8")
    for marker in markers:
        require(marker in text, f"{path.relative_to(ROOT)} missing authorization marker: {marker}")


def main() -> int:
    collector = load_module(COLLECTOR, "lumi_release_authorization")
    result: dict[str, Any] = collector.self_test()
    require(result.get("status") == "PASS", "release authorization self-test did not PASS")
    require(result.get("negative_drills") == 8, "release authorization negative drill count drift")
    distinct = result.get("clean_distinct_approvers")
    require(isinstance(distinct, int) and distinct >= 3, "clean authorization fixture must use at least three distinct approvers")

    policy = json.loads(POLICY_TEMPLATE.read_text(encoding="utf-8"))
    require(policy.get("kind") == collector.POLICY_KIND, "approval policy template kind mismatch")
    require(policy.get("repository") == collector.EXPECTED_REPOSITORY, "approval policy template repository mismatch")
    require(policy.get("pull_request") == collector.EXPECTED_PR, "approval policy template PR mismatch")
    require(policy.get("base_ref") == collector.EXPECTED_BASE_REF, "approval policy template base ref mismatch")
    require(policy.get("head_ref") == collector.EXPECTED_HEAD_REF, "approval policy template head ref mismatch")
    require(policy.get("minimum_distinct_actors") == 3, "approval policy template distinct actor floor must be 3")
    roles = policy.get("roles")
    require(isinstance(roles, dict) and set(roles) == set(collector.ROLES), "approval policy template role set mismatch")
    for role in collector.ROLES:
        require(
            roles[role].get("allowed_logins") == ["PENDING"],
            f"approval policy template role {role} must remain fail-closed until real principals are configured",
        )

    request = json.loads(REQUEST_TEMPLATE.read_text(encoding="utf-8"))
    require(request.get("kind") == collector.REQUEST_KIND, "authorization request template kind mismatch")
    require(request.get("repository") == collector.EXPECTED_REPOSITORY, "authorization request template repository mismatch")
    require(request.get("pull_request") == collector.EXPECTED_PR, "authorization request template PR mismatch")
    require(request.get("approval_policy") == {"path": "PENDING", "sha256": "PENDING"}, "authorization request template must freeze approval policy")

    authorization = json.loads(AUTH_TEMPLATE.read_text(encoding="utf-8"))
    require(authorization.get("kind") == collector.AUTHORIZATION_KIND, "authorization output template kind mismatch")
    require(authorization.get("status") == "PENDING", "authorization output template must start PENDING")
    require(authorization.get("repository") == collector.EXPECTED_REPOSITORY, "authorization output template repository mismatch")
    require(authorization.get("distinct_approver_count") == 0, "authorization output template must not pre-approve actors")
    auth_roles = authorization.get("approvals")
    require(isinstance(auth_roles, dict) and set(auth_roles) == set(collector.ROLES), "authorization output template role set mismatch")
    for role in collector.ROLES:
        item = auth_roles[role]
        require(isinstance(item, dict), f"authorization output template role {role} must be structured")
        require(item.get("status") == "PENDING", f"authorization output template role {role} must start PENDING")
        for field in ("actor", "review_url", "commit_id", "submitted_at"):
            require(item.get(field) == "PENDING", f"authorization output template role {role}.{field} must start PENDING")
        require(item.get("review_id") == 0, f"authorization output template role {role}.review_id must start zero")

    require_markers(
        COLLECTOR,
        (
            'EXPECTED_PR = 135',
            'EXPECTED_BASE_REF = "node-73-final-acceptance-release"',
            'EXPECTED_HEAD_REF = "release-closure-p0"',
            'minimum_distinct_actors',
            'MANDATORY_SOD',
            'not login.endswith("[bot]")',
            'actor == pr_author or actor.endswith("[bot]")',
            'review.get("state") != "APPROVED"',
            'commit_id.lower() != rc_sha.lower()',
            'latest_decisive_reviews',
            'validate_authorization_report(',
            'verify_live_authorization(',
            'live GitHub review is no longer APPROVED',
            'frozen approval is not the latest decisive review',
            'os.environ.get("RELEASE_APPROVAL_TOKEN")',
        ),
    )
    require_markers(
        ASSEMBLER,
        (
            'AUTHORIZATION_VALIDATOR = ROOT / "scripts" / "capture_release_authorization.py"',
            'validator.validate_authorization_report(',
            'expected_release_id=release_id',
            'expected_rc=expected_rc',
            'canonical release authorization did not yield all APPROVED statuses',
        ),
    )
    require_markers(
        PACKAGE_VALIDATOR,
        (
            'AUTHORIZATION_VALIDATOR = ROOT / "scripts" / "capture_release_authorization.py"',
            'validate_release_authorization(',
            'validator.validate_authorization_report(',
            'release approval statuses differ from validated GitHub authorization',
            'release operational handoff differs from validated authorization request',
        ),
    )
    require_markers(
        ASSEMBLER_CONTRACT,
        (
            'AUTHORIZATION_VALIDATOR_PATH = ROOT / "scripts/capture_release_authorization.py"',
            'build_authorization_fixture(',
            'authorization_validator.build_authorization(',
            'authorization actor swap',
            'authorization RC commit swap',
            'authorization policy hash tamper',
        ),
    )

    workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")
    require(
        "pull-requests: read" in workflow,
        "Final Decision must receive read-only Pull Requests permission for live approval verification",
    )
    for marker in (
        'RELEASE_APPROVAL_TOKEN: ${{ secrets.GITHUB_TOKEN }}',
        'name: Re-verify live GitHub release authorization for frozen RC',
        'python3 scripts/capture_release_authorization.py',
        '--verify-report "$authorization_path"',
        '--live-output reports/final-acceptance/runtime/release-authorization-live.json',
        'reports/final-acceptance/runtime/release-authorization-live.json',
    ):
        require(marker in workflow, f"Final Decision missing live authorization marker: {marker}")
    governance_pos = workflow.find("name: Re-verify live strong repository governance for frozen RC")
    authorization_pos = workflow.find("name: Re-verify live GitHub release authorization for frozen RC")
    decision_pos = workflow.find("name: Evaluate final product acceptance")
    require(
        min(governance_pos, authorization_pos, decision_pos) >= 0
        and governance_pos < authorization_pos < decision_pos,
        "Final Decision must reverify repository governance, then human authorization, then product acceptance",
    )

    print("NODE-73 GitHub-backed final authorization source contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AuthorizationContractError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"release authorization contract failed: {exc}") from exc

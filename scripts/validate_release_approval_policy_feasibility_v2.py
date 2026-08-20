#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION_V2 = ROOT / "scripts" / "capture_release_authorization_v2.py"


class ApprovalPolicyFeasibilityError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ApprovalPolicyFeasibilityError(message)


def load_auth() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_release_authorization_policy_feasibility", AUTHORIZATION_V2)
    if spec is None or spec.loader is None:
        raise ApprovalPolicyFeasibilityError("unable to import canonical V2 authorization validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def feasible_assignment(policy: Mapping[str, Any], roles: tuple[str, ...]) -> dict[str, str] | None:
    candidates = {
        role: list(policy["roles"][role]["allowed_logins"])
        for role in roles
    }
    minimum = int(policy["minimum_distinct_actors"])
    sod = {tuple(sorted(pair)) for pair in policy["separation_of_duties"]}
    assignment: dict[str, str] = {}

    def compatible(role: str, actor: str) -> bool:
        for other_role, other_actor in assignment.items():
            if tuple(sorted((role, other_role))) in sod and actor == other_actor:
                return False
        return True

    def search(index: int) -> bool:
        if index == len(roles):
            return len(set(assignment.values())) >= minimum
        role = roles[index]
        for actor in sorted(candidates[role], key=lambda value: (value in assignment.values(), value)):
            if not compatible(role, actor):
                continue
            assignment[role] = actor
            if search(index + 1):
                return True
            assignment.pop(role, None)
        return False

    return dict(assignment) if search(0) else None


def validate_policy(payload: Mapping[str, Any]) -> dict[str, Any]:
    auth = load_auth()
    try:
        normalized = auth.validate_policy(payload)
    except auth.ReleaseAuthorizationV2Error as exc:
        raise ApprovalPolicyFeasibilityError(f"approval policy syntax/identity invalid: {exc}") from exc
    assignment = feasible_assignment(normalized, tuple(auth.ROLES))
    require(
        assignment is not None,
        "approval principal allowlists cannot satisfy minimum distinct actors and separation-of-duties policy",
    )
    distinct_candidates = sorted(
        {
            login
            for role in auth.ROLES
            for login in normalized["roles"][role]["allowed_logins"]
        }
    )
    return {
        "schema_version": 1,
        "kind": "LUMI_RELEASE_APPROVAL_POLICY_FEASIBILITY_V2",
        "status": "PASS",
        "minimum_distinct_actors": normalized["minimum_distinct_actors"],
        "distinct_candidate_count": len(distinct_candidates),
        "distinct_candidates": distinct_candidates,
        "feasible_assignment": assignment,
        "policy": normalized,
    }


def fixture() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "kind": "LUMI_RELEASE_APPROVAL_POLICY_V2",
        "repository": "zhangjaky71-stack/LUMI-AI-DESIGN-OS",
        "pull_request": 135,
        "base_ref": "node-73-final-acceptance-release",
        "head_ref": "release-closure-p0",
        "minimum_distinct_actors": 3,
        "roles": {
            "product": {"allowed_logins": ["alice"]},
            "engineering": {"allowed_logins": ["bob"]},
            "security": {"allowed_logins": ["carol"]},
            "operations": {"allowed_logins": ["alice", "dave"]},
            "release_owner": {"allowed_logins": ["dave"]},
        },
        "separation_of_duties": [
            ["engineering", "security"],
            ["security", "release_owner"],
        ],
        "require_human_reviewers": True,
        "require_exact_evidence_head_review_commit": True,
        "require_pr_author_exclusion": True,
        "require_latest_decisive_review": True,
    }


def self_test() -> dict[str, Any]:
    clean = validate_policy(fixture())
    require(len(set(clean["feasible_assignment"].values())) >= 3, "clean fixture did not prove three distinct approvers")

    mutations: list[dict[str, Any]] = []
    one_actor = json.loads(json.dumps(fixture()))
    for role in one_actor["roles"].values():
        role["allowed_logins"] = ["alice"]
    mutations.append(one_actor)

    two_actors = json.loads(json.dumps(fixture()))
    two_actors["roles"] = {
        "product": {"allowed_logins": ["alice"]},
        "engineering": {"allowed_logins": ["alice"]},
        "security": {"allowed_logins": ["bob"]},
        "operations": {"allowed_logins": ["alice", "bob"]},
        "release_owner": {"allowed_logins": ["alice"]},
    }
    mutations.append(two_actors)

    sod_impossible = json.loads(json.dumps(fixture()))
    sod_impossible["roles"]["engineering"] = {"allowed_logins": ["alice"]}
    sod_impossible["roles"]["security"] = {"allowed_logins": ["alice"]}
    mutations.append(sod_impossible)

    five_required_four_available = json.loads(json.dumps(fixture()))
    five_required_four_available["minimum_distinct_actors"] = 5
    mutations.append(five_required_four_available)

    blocked = 0
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate_policy(mutation)
        except ApprovalPolicyFeasibilityError:
            blocked += 1
            continue
        raise ApprovalPolicyFeasibilityError(f"negative approval-policy feasibility drill did not block: {index}")
    return {"status": "PASS", "clean": clean, "negative_drills": blocked}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate NODE-73 V2 approval principal policy feasibility")
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    require(args.policy is not None, "--policy is required unless --self-test is used")
    payload = json.loads(args.policy.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "approval policy must be a JSON object")
    print(json.dumps(validate_policy(payload), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ApprovalPolicyFeasibilityError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"release approval policy feasibility blocked: {exc}") from exc

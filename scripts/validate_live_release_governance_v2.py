#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
POLICY_VALIDATOR = ROOT / "scripts" / "validate_release_governance_policy.py"
BRANCH_VALIDATOR = ROOT / "scripts" / "capture_release_branch_protection.py"


class LiveGovernanceV2Error(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveGovernanceV2Error(message)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise LiveGovernanceV2Error(f"unable to import {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_live_report(
    report: Mapping[str, Any],
    policy_payload: Mapping[str, Any],
    *,
    expected_repository: str,
    expected_evidence_head_sha: str,
) -> dict[str, Any]:
    policy_module = load_module(POLICY_VALIDATOR, "lumi_release_governance_policy_live_v2")
    branch_module = load_module(BRANCH_VALIDATOR, "lumi_release_branch_protection_live_v2")
    try:
        policy = policy_module.validate_policy(policy_payload)
    except policy_module.GovernancePolicyError as exc:
        raise LiveGovernanceV2Error(f"frozen governance policy invalid: {exc}") from exc
    require(policy.get("repository") == expected_repository, "governance policy repository differs from live repository")

    try:
        base = branch_module.validate_report(
            report,
            expected_repository=expected_repository,
            expected_release_sha=expected_evidence_head_sha,
        )
    except branch_module.BranchProtectionError as exc:
        raise LiveGovernanceV2Error(f"live branch protection invalid: {exc}") from exc

    required_checks = policy.get("required_status_checks")
    require(isinstance(required_checks, Mapping), "normalized governance policy required_status_checks missing")
    required_contexts_raw = required_checks.get("required_contexts")
    require(isinstance(required_contexts_raw, list) and bool(required_contexts_raw), "normalized required status contexts missing")
    required_contexts = {str(value) for value in required_contexts_raw}
    allow_additional = required_checks.get("allow_additional_contexts") is True

    branches = report.get("branches")
    require(isinstance(branches, list), "live governance branches missing")
    branch_contexts: dict[str, list[str]] = {}
    expected_branches = set(policy.get("release_branches", []))
    for item in branches:
        require(isinstance(item, Mapping), "live governance branch entry invalid")
        name = item.get("name")
        if not isinstance(name, str) or name not in expected_branches:
            continue
        protection = item.get("protection")
        require(isinstance(protection, Mapping), f"live strong protection missing for {name}")
        status_checks = protection.get("required_status_checks")
        require(isinstance(status_checks, Mapping), f"live required status checks missing for {name}")
        require(status_checks.get("strict") is True, f"live required status checks are not strict for {name}")
        contexts_raw = status_checks.get("contexts")
        require(isinstance(contexts_raw, list), f"live required status context list missing for {name}")
        observed = {str(value) for value in contexts_raw if isinstance(value, str) and value}
        missing = sorted(required_contexts - observed)
        require(not missing, f"live branch {name} is missing canonical required status contexts: {missing}")
        if not allow_additional:
            require(observed == required_contexts, f"live branch {name} has unapproved additional required status contexts")
        branch_contexts[name] = sorted(observed)

    require(set(branch_contexts) == expected_branches, "live governance did not validate every policy release branch")
    return {
        **base,
        "policy_kind": policy.get("kind"),
        "required_status_contexts": sorted(required_contexts),
        "branch_status_contexts": branch_contexts,
        "status_check_policy_bound": True,
    }


def _policy() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "LUMI_RELEASE_GOVERNANCE_POLICY_V1",
        "repository": "zhangjaky71-stack/LUMI-AI-DESIGN-OS",
        "release_branches": ["node-73-final-acceptance-release", "release-closure-p0"],
        "evidence_head_branch": "release-closure-p0",
        "protection_profile": "LUMI_RELEASE_PROTECTION_PROFILE_V1",
        "required_status_checks": {
            "strict": True,
            "required_contexts": ["node73-final-contract-gate"],
            "allow_additional_contexts": True,
        },
        "require_live_reverification": True,
        "require_evidence_head_equals_execution_sha": True,
    }


def _profile(contexts: list[str]) -> dict[str, Any]:
    return {
        "profile": "LUMI_RELEASE_PROTECTION_PROFILE_V1",
        "required_status_checks": {"strict": True, "contexts": contexts, "count": len(contexts)},
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "require_last_push_approval": True,
            "bypass_actor_count": 0,
            "require_code_owner_reviews": False,
        },
        "required_linear_history": True,
        "required_conversation_resolution": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_signatures": False,
    }


def self_test() -> dict[str, Any]:
    repository = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
    evidence = "b" * 40
    canonical = "node73-final-contract-gate"
    report = {
        "schema_version": 1,
        "kind": "LUMI_RELEASE_BRANCH_PROTECTION_V1",
        "status": "PASS",
        "repository": repository,
        "branches": [
            {
                "name": "node-73-final-acceptance-release",
                "protected": True,
                "head_sha": "a" * 40,
                "protection": _profile([canonical, "extra-security-check"]),
            },
            {
                "name": "release-closure-p0",
                "protected": True,
                "head_sha": evidence,
                "protection": _profile([canonical]),
            },
        ],
    }
    clean = validate_live_report(
        report,
        _policy(),
        expected_repository=repository,
        expected_evidence_head_sha=evidence,
    )
    require(clean.get("status_check_policy_bound") is True, "clean live governance fixture did not bind policy")

    blocked = 0
    mutations: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    missing_base = json.loads(json.dumps(report))
    missing_base["branches"][0]["protection"]["required_status_checks"] = {"strict": True, "contexts": ["other"], "count": 1}
    mutations.append((missing_base, _policy(), evidence))
    missing_head = json.loads(json.dumps(report))
    missing_head["branches"][1]["protection"]["required_status_checks"] = {"strict": True, "contexts": ["other"], "count": 1}
    mutations.append((missing_head, _policy(), evidence))
    weak_policy = _policy()
    weak_policy["required_status_checks"]["required_contexts"] = ["other"]
    mutations.append((report, weak_policy, evidence))
    mutations.append((report, _policy(), "c" * 40))

    for index, (candidate_report, candidate_policy, candidate_sha) in enumerate(mutations, start=1):
        try:
            validate_live_report(
                candidate_report,
                candidate_policy,
                expected_repository=repository,
                expected_evidence_head_sha=candidate_sha,
            )
        except LiveGovernanceV2Error:
            blocked += 1
            continue
        raise LiveGovernanceV2Error(f"negative live-governance V2 drill did not block: {index}")
    return {"status": "PASS", "clean": clean, "negative_drills": blocked}


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind live NODE-73 branch protection to the frozen governance policy")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--repository")
    parser.add_argument("--evidence-head-sha")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    require(args.report is not None and args.policy is not None, "--report and --policy are required")
    require(isinstance(args.repository, str) and bool(args.repository), "--repository is required")
    require(isinstance(args.evidence_head_sha, str) and bool(args.evidence_head_sha), "--evidence-head-sha is required")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    require(isinstance(report, dict) and isinstance(policy, dict), "report and policy must be JSON objects")
    print(
        json.dumps(
            validate_live_report(
                report,
                policy,
                expected_repository=args.repository,
                expected_evidence_head_sha=args.evidence_head_sha,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LiveGovernanceV2Error, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"live release governance V2 blocked: {exc}") from exc

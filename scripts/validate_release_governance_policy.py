#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
KIND = "LUMI_RELEASE_GOVERNANCE_POLICY_V1"
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
REQUIRED_BRANCHES = {
    "node-73-final-acceptance-release",
    "release-closure-p0",
}
EVIDENCE_HEAD_BRANCH = "release-closure-p0"
PROTECTION_PROFILE = "LUMI_RELEASE_PROTECTION_PROFILE_V1"


class GovernancePolicyError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GovernancePolicyError(message)


def validate_policy(payload: Mapping[str, Any]) -> dict[str, Any]:
    require(payload.get("schema_version") == 1, "governance policy schema_version must be 1")
    require(payload.get("kind") == KIND, "governance policy kind mismatch")
    require(payload.get("repository") == EXPECTED_REPOSITORY, "governance policy repository mismatch")
    branches = payload.get("release_branches")
    require(isinstance(branches, list) and len(branches) == 2, "governance policy must define exactly two release branches")
    require(set(branches) == REQUIRED_BRANCHES and len(set(branches)) == 2, "governance policy release branch set mismatch")
    require(payload.get("evidence_head_branch") == EVIDENCE_HEAD_BRANCH, "governance policy evidence head branch mismatch")
    require(payload.get("protection_profile") == PROTECTION_PROFILE, "governance policy strong protection profile mismatch")
    require(payload.get("require_live_reverification") is True, "governance policy must require live re-verification")
    require(payload.get("require_evidence_head_equals_execution_sha") is True, "governance policy must bind live branch head to execution SHA")
    return {
        "schema_version": 1,
        "kind": KIND,
        "repository": EXPECTED_REPOSITORY,
        "release_branches": sorted(REQUIRED_BRANCHES),
        "evidence_head_branch": EVIDENCE_HEAD_BRANCH,
        "protection_profile": PROTECTION_PROFILE,
        "require_live_reverification": True,
        "require_evidence_head_equals_execution_sha": True,
    }


def self_test() -> dict[str, Any]:
    good = {
        "schema_version": 1,
        "kind": KIND,
        "repository": EXPECTED_REPOSITORY,
        "release_branches": sorted(REQUIRED_BRANCHES),
        "evidence_head_branch": EVIDENCE_HEAD_BRANCH,
        "protection_profile": PROTECTION_PROFILE,
        "require_live_reverification": True,
        "require_evidence_head_equals_execution_sha": True,
    }
    clean = validate_policy(good)
    mutations = [
        {**good, "repository": "example/other"},
        {**good, "release_branches": [EVIDENCE_HEAD_BRANCH]},
        {**good, "evidence_head_branch": "node-73-final-acceptance-release"},
        {**good, "protection_profile": "WEAK"},
        {**good, "require_live_reverification": False},
        {**good, "require_evidence_head_equals_execution_sha": False},
    ]
    blocked = 0
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate_policy(mutation)
        except GovernancePolicyError:
            blocked += 1
            continue
        raise GovernancePolicyError(f"negative governance policy drill did not block: {index}")
    return {"status": "PASS", "clean": clean, "negative_drills": blocked}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate NODE-73 pre-final repository-governance policy")
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    require(args.policy is not None, "--policy is required unless --self-test is used")
    payload = json.loads(args.policy.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "governance policy must be a JSON object")
    print(json.dumps(validate_policy(payload), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GovernancePolicyError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"release governance policy blocked: {exc}") from exc

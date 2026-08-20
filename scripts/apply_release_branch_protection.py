#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
POLICY_VALIDATOR = ROOT / "scripts" / "validate_release_governance_policy.py"
BRANCH_CAPTURE = ROOT / "scripts" / "capture_release_branch_protection.py"
LIVE_BINDER = ROOT / "scripts" / "validate_live_release_governance_v2.py"
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
CONFIRMATION = "APPLY_NODE73_RELEASE_PROTECTION"


class BranchProtectionApplyError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BranchProtectionApplyError(message)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BranchProtectionApplyError(f"unable to import {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), f"{path} must contain a JSON object")
    return payload


def render_protection_body(policy: Mapping[str, Any]) -> dict[str, Any]:
    checks = policy.get("required_status_checks")
    require(isinstance(checks, Mapping), "normalized policy required_status_checks missing")
    contexts = checks.get("required_contexts")
    require(isinstance(contexts, list) and bool(contexts), "normalized policy required status contexts missing")
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": list(contexts),
        },
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "required_approving_review_count": 1,
            "require_last_push_approval": True,
        },
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": True,
        "lock_branch": False,
        "allow_fork_syncing": False,
    }


def put_json(url: str, *, token: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        method="PUT",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "lumi-node73-release-protection-apply",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise BranchProtectionApplyError(
            f"GitHub branch protection update failed with HTTP {exc.code}: {detail}. "
            "Use a fine-grained token with repository Administration write permission; "
            "HTTP 422 can also mean the canonical required check is not yet eligible/configurable."
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BranchProtectionApplyError(f"GitHub branch protection update failed: {exc}") from exc
    require(isinstance(result, dict), "GitHub branch protection update returned non-object JSON")
    return result


def apply(
    *,
    repository: str,
    policy_path: Path,
    evidence_head_sha: str,
    token: str,
    confirmation: str,
) -> dict[str, Any]:
    require(repository == EXPECTED_REPOSITORY, "repository identity mismatch")
    require(confirmation == CONFIRMATION, f"explicit confirmation must equal {CONFIRMATION}")
    require(len(evidence_head_sha) == 40 and all(char in "0123456789abcdefABCDEF" for char in evidence_head_sha), "Evidence Head SHA must be exact SHA40")
    require(bool(token.strip()), "RELEASE_GOVERNANCE_ADMIN_TOKEN is required")

    policy_module = load_module(POLICY_VALIDATOR, "lumi_release_governance_apply_policy")
    capture_module = load_module(BRANCH_CAPTURE, "lumi_release_governance_apply_capture")
    binder_module = load_module(LIVE_BINDER, "lumi_release_governance_apply_binder")
    try:
        policy = policy_module.validate_policy(load_json(policy_path))
    except policy_module.GovernancePolicyError as exc:
        raise BranchProtectionApplyError(f"governance policy invalid: {exc}") from exc
    body = render_protection_body(policy)

    preflight_heads: dict[str, str] = {}
    for branch in policy["release_branches"]:
        try:
            branch_payload = capture_module._fetch_branch(repository, branch, token=token)
        except capture_module.BranchProtectionError as exc:
            raise BranchProtectionApplyError(f"pre-apply branch lookup failed for {branch}: {exc}") from exc
        commit = branch_payload.get("commit")
        sha = commit.get("sha") if isinstance(commit, Mapping) else None
        require(isinstance(sha, str) and len(sha) == 40, f"pre-apply branch head SHA missing for {branch}")
        preflight_heads[branch] = sha.lower()
    evidence_branch = policy["evidence_head_branch"]
    require(
        preflight_heads.get(evidence_branch) == evidence_head_sha.lower(),
        "release-closure-p0 moved after dispatch; refusing to apply branch protection to a different Evidence Head",
    )

    applied: list[dict[str, Any]] = []
    for branch in policy["release_branches"]:
        response = put_json(
            f"https://api.github.com/repos/{repository}/branches/{branch}/protection",
            token=token,
            payload=body,
        )
        applied.append(
            {
                "branch": branch,
                "required_status_checks": response.get("required_status_checks"),
                "enforce_admins": response.get("enforce_admins"),
                "required_pull_request_reviews": response.get("required_pull_request_reviews"),
            }
        )

    live_report = capture_module.capture(repository, token=token)
    try:
        live_result = binder_module.validate_live_report(
            live_report,
            policy,
            expected_repository=repository,
            expected_evidence_head_sha=evidence_head_sha.lower(),
        )
    except binder_module.LiveGovernanceV2Error as exc:
        raise BranchProtectionApplyError(f"post-apply live governance verification failed: {exc}") from exc
    return {
        "schema_version": 1,
        "kind": "LUMI_RELEASE_BRANCH_PROTECTION_APPLY_V1",
        "status": "PASS",
        "repository": repository,
        "evidence_head_sha": evidence_head_sha.lower(),
        "preflight_heads": preflight_heads,
        "policy": policy,
        "request_body": body,
        "applied": applied,
        "live_report": live_report,
        "live_validation": live_result,
    }


def self_test() -> dict[str, Any]:
    policy = {
        "schema_version": 1,
        "kind": "LUMI_RELEASE_GOVERNANCE_POLICY_V1",
        "repository": EXPECTED_REPOSITORY,
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
    policy_module = load_module(POLICY_VALIDATOR, "lumi_release_governance_apply_selftest")
    normalized = policy_module.validate_policy(policy)
    body = render_protection_body(normalized)
    require(body["required_status_checks"] == {"strict": True, "contexts": ["node73-final-contract-gate"]}, "canonical required check payload drift")
    require(body["enforce_admins"] is True, "admin enforcement must be enabled")
    require(body["allow_force_pushes"] is False and body["allow_deletions"] is False, "unsafe branch mutations must remain disabled")
    reviews = body["required_pull_request_reviews"]
    require(reviews["dismiss_stale_reviews"] is True, "stale review dismissal must remain enabled")
    require(reviews["require_last_push_approval"] is True, "last-push approval must remain enabled")
    require(reviews["required_approving_review_count"] >= 1, "at least one protected-branch approval must be required")
    return {"status": "PASS", "request_body": body, "preflight_guard": "EVIDENCE_HEAD_EXACT", "negative_network_calls": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply canonical NODE-73 release branch protection")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--policy", type=Path, default=ROOT / "final/acceptance/repository-governance-policy-template.json")
    parser.add_argument("--evidence-head-sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--confirm", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    result = apply(
        repository=args.repository,
        policy_path=args.policy,
        evidence_head_sha=args.evidence_head_sha,
        token=os.environ.get("RELEASE_GOVERNANCE_ADMIN_TOKEN", ""),
        confirmation=args.confirm,
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BranchProtectionApplyError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"release branch protection apply blocked: {exc}") from exc

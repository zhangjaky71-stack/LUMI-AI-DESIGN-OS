#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SHA40 = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REQUIRED_BRANCHES = (
    "node-73-final-acceptance-release",
    "release-closure-p0",
)
RELEASE_HEAD_BRANCH = "release-closure-p0"
KIND = "LUMI_RELEASE_BRANCH_PROTECTION_V1"
PROFILE = "LUMI_RELEASE_PROTECTION_PROFILE_V1"


class BranchProtectionError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BranchProtectionError(message)


def _enabled(payload: Mapping[str, Any], key: str) -> bool:
    item = payload.get(key)
    return isinstance(item, Mapping) and item.get("enabled") is True


def _disabled(payload: Mapping[str, Any], key: str) -> bool:
    item = payload.get(key)
    return isinstance(item, Mapping) and item.get("enabled") is False


def normalize_protection_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    status_checks = payload.get("required_status_checks")
    _require(isinstance(status_checks, Mapping), "required status checks must be enabled")
    _require(status_checks.get("strict") is True, "required status checks must require the branch to be up to date")
    names: set[str] = set()
    contexts = status_checks.get("contexts")
    if isinstance(contexts, list):
        names.update(str(value) for value in contexts if isinstance(value, str) and value.strip())
    checks = status_checks.get("checks")
    if isinstance(checks, list):
        for item in checks:
            if isinstance(item, Mapping):
                context = item.get("context")
                if isinstance(context, str) and context.strip():
                    names.add(context)
    _require(bool(names), "at least one required status check is mandatory")

    enforce_admins = payload.get("enforce_admins")
    _require(
        isinstance(enforce_admins, Mapping) and enforce_admins.get("enabled") is True,
        "branch protection must enforce rules for administrators",
    )

    reviews = payload.get("required_pull_request_reviews")
    _require(isinstance(reviews, Mapping), "pull request reviews must be required")
    count = reviews.get("required_approving_review_count")
    _require(isinstance(count, int) and not isinstance(count, bool) and count >= 1, "at least one approving PR review is required")
    _require(reviews.get("dismiss_stale_reviews") is True, "stale approving reviews must be dismissed after new pushes")
    _require(reviews.get("require_last_push_approval") is True, "the latest reviewable push must be approved by another actor")
    bypass = reviews.get("bypass_pull_request_allowances")
    bypass_count = 0
    if isinstance(bypass, Mapping):
        for key in ("users", "teams", "apps"):
            values = bypass.get(key)
            if isinstance(values, list):
                bypass_count += len(values)
    _require(bypass_count == 0, "pull request approval bypass allowances are not permitted for final release refs")

    _require(_enabled(payload, "required_linear_history"), "linear history must be required")
    _require(
        _enabled(payload, "required_conversation_resolution"),
        "review conversations must be resolved before merge",
    )
    _require(_disabled(payload, "allow_force_pushes"), "force pushes must be disabled")
    _require(_disabled(payload, "allow_deletions"), "branch deletions must be disabled")

    signatures = payload.get("required_signatures")
    signatures_enabled = isinstance(signatures, Mapping) and signatures.get("enabled") is True
    lock_branch = payload.get("lock_branch")
    lock_enabled = isinstance(lock_branch, Mapping) and lock_branch.get("enabled") is True
    allow_fork_syncing = payload.get("allow_fork_syncing")
    fork_sync_enabled = isinstance(allow_fork_syncing, Mapping) and allow_fork_syncing.get("enabled") is True
    return {
        "profile": PROFILE,
        "required_status_checks": {
            "strict": True,
            "contexts": sorted(names),
            "count": len(names),
        },
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "required_approving_review_count": count,
            "dismiss_stale_reviews": True,
            "require_last_push_approval": True,
            "bypass_actor_count": 0,
            "require_code_owner_reviews": reviews.get("require_code_owner_reviews") is True,
        },
        "required_linear_history": True,
        "required_conversation_resolution": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_signatures": signatures_enabled,
        "lock_branch": lock_enabled,
        "allow_fork_syncing": fork_sync_enabled,
    }


def validate_normalized_profile(profile: Mapping[str, Any]) -> None:
    _require(profile.get("profile") == PROFILE, "release protection profile identifier mismatch")
    checks = profile.get("required_status_checks")
    _require(isinstance(checks, Mapping), "normalized required status checks are missing")
    _require(checks.get("strict") is True, "normalized status checks are not strict")
    count = checks.get("count")
    contexts = checks.get("contexts")
    _require(isinstance(count, int) and not isinstance(count, bool) and count >= 1, "normalized required status check count is invalid")
    _require(isinstance(contexts, list) and len(contexts) == count, "normalized required status check contexts are invalid")
    _require(all(isinstance(value, str) and value for value in contexts), "normalized required status check context is invalid")
    _require(profile.get("enforce_admins") is True, "normalized admin enforcement is disabled")
    reviews = profile.get("required_pull_request_reviews")
    _require(isinstance(reviews, Mapping), "normalized PR review policy missing")
    review_count = reviews.get("required_approving_review_count")
    _require(isinstance(review_count, int) and not isinstance(review_count, bool) and review_count >= 1, "normalized PR approving review count is invalid")
    _require(reviews.get("dismiss_stale_reviews") is True, "normalized stale review dismissal is disabled")
    _require(reviews.get("require_last_push_approval") is True, "normalized last-push approval is disabled")
    _require(reviews.get("bypass_actor_count") == 0, "normalized PR bypass actor count must be zero")
    _require(profile.get("required_linear_history") is True, "normalized linear history is disabled")
    _require(profile.get("required_conversation_resolution") is True, "normalized conversation resolution is disabled")
    _require(profile.get("allow_force_pushes") is False, "normalized force-push policy is unsafe")
    _require(profile.get("allow_deletions") is False, "normalized branch deletion policy is unsafe")
    _require(isinstance(profile.get("required_signatures"), bool), "normalized signed-commit observation must be boolean")
    _require(isinstance(profile.get("lock_branch"), bool), "normalized branch-lock observation must be boolean")
    _require(isinstance(profile.get("allow_fork_syncing"), bool), "normalized fork-sync observation must be boolean")


def validate_branch_payload(
    name: str,
    payload: Mapping[str, Any],
    *,
    protection_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _require(name in REQUIRED_BRANCHES, f"unexpected release branch: {name}")
    _require(payload.get("name") == name, f"GitHub branch response name mismatch for {name}")
    protected = payload.get("protected")
    _require(isinstance(protected, bool), f"GitHub branch protected flag missing for {name}")
    commit = payload.get("commit")
    _require(isinstance(commit, Mapping), f"GitHub branch commit missing for {name}")
    sha = commit.get("sha")
    _require(isinstance(sha, str) and bool(SHA40.fullmatch(sha.lower())), f"GitHub branch head SHA invalid for {name}")
    profile = None
    if protected:
        _require(isinstance(protection_payload, Mapping), f"detailed branch protection is unavailable for {name}")
        profile = normalize_protection_payload(protection_payload)
    return {
        "name": name,
        "protected": protected,
        "head_sha": sha.lower(),
        "protection": profile,
    }


def validate_report(
    report: Mapping[str, Any],
    *,
    expected_repository: str,
    expected_release_sha: str | None = None,
) -> dict[str, Any]:
    _require(report.get("schema_version") == 1, "branch protection report schema_version must be 1")
    _require(report.get("kind") == KIND, "branch protection report kind mismatch")
    _require(report.get("repository") == expected_repository, "branch protection report repository mismatch")
    branches = report.get("branches")
    _require(isinstance(branches, list) and len(branches) == len(REQUIRED_BRANCHES), "branch protection report must contain exactly two release branches")
    by_name: dict[str, Mapping[str, Any]] = {}
    for item in branches:
        _require(isinstance(item, Mapping), "branch protection report branch entry must be an object")
        name = item.get("name")
        _require(isinstance(name, str) and name in REQUIRED_BRANCHES and name not in by_name, f"invalid/duplicate branch protection entry: {name}")
        by_name[name] = item
    _require(set(by_name) == set(REQUIRED_BRANCHES), "branch protection report branch set mismatch")
    for name in REQUIRED_BRANCHES:
        item = by_name[name]
        _require(item.get("protected") is True, f"release branch is not protected: {name}")
        sha = item.get("head_sha")
        _require(isinstance(sha, str) and bool(SHA40.fullmatch(sha.lower())), f"release branch head SHA invalid: {name}")
        profile = item.get("protection")
        _require(isinstance(profile, Mapping), f"release branch strong protection profile missing: {name}")
        validate_normalized_profile(profile)
    if expected_release_sha is not None:
        _require(bool(SHA40.fullmatch(expected_release_sha.lower())), "expected release SHA must be SHA40")
        _require(
            by_name[RELEASE_HEAD_BRANCH].get("head_sha") == expected_release_sha.lower(),
            "release-closure-p0 head SHA does not equal the final release candidate SHA",
        )
    _require(report.get("status") == "PASS", "branch protection report status must be PASS")
    return {
        "status": "PASS",
        "repository": expected_repository,
        "release_head_sha": by_name[RELEASE_HEAD_BRANCH]["head_sha"],
        "protected_branch_count": len(REQUIRED_BRANCHES),
        "protection_profile": PROFILE,
    }


def _fetch_json(url: str, *, token: str | None, label: str) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "lumi-node73-release-branch-protection",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BranchProtectionError(
            f"{label} failed with HTTP {exc.code}; a fine-grained token with repository Administration read permission is required for detailed protection evidence"
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BranchProtectionError(f"{label} failed: {exc}") from exc
    _require(isinstance(payload, dict), f"{label} returned non-object JSON")
    return payload


def _fetch_branch(repository: str, branch: str, *, token: str | None) -> dict[str, Any]:
    return _fetch_json(
        f"https://api.github.com/repos/{repository}/branches/{branch}",
        token=token,
        label=f"GitHub branch lookup for {branch}",
    )


def _fetch_protection(repository: str, branch: str, *, token: str | None) -> dict[str, Any]:
    _require(bool(token), "detailed branch protection capture requires an Administration-read GitHub token")
    return _fetch_json(
        f"https://api.github.com/repos/{repository}/branches/{branch}/protection",
        token=token,
        label=f"GitHub branch protection lookup for {branch}",
    )


def capture(repository: str, *, token: str | None) -> dict[str, Any]:
    _require(bool(REPOSITORY.fullmatch(repository)), "repository must use OWNER/REPO form")
    branches: list[dict[str, Any]] = []
    for name in REQUIRED_BRANCHES:
        branch_payload = _fetch_branch(repository, name, token=token)
        protected = branch_payload.get("protected") is True
        protection_payload = _fetch_protection(repository, name, token=token) if protected else None
        branches.append(
            validate_branch_payload(
                name,
                branch_payload,
                protection_payload=protection_payload,
            )
        )
    all_strongly_protected = all(
        item["protected"] is True and isinstance(item.get("protection"), Mapping)
        for item in branches
    )
    return {
        "schema_version": 1,
        "kind": KIND,
        "status": "PASS" if all_strongly_protected else "BLOCKED_EXTERNAL",
        "repository": repository,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "branches": branches,
    }


def _profile_fixture() -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "required_status_checks": {
            "strict": True,
            "contexts": ["Final Product Acceptance Gate / contract-gate"],
            "count": 1,
        },
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
        "lock_branch": False,
        "allow_fork_syncing": False,
    }


def self_test() -> dict[str, Any]:
    repository = "example/lumi"
    release_sha = "a" * 40
    profile = _profile_fixture()
    good = {
        "schema_version": 1,
        "kind": KIND,
        "status": "PASS",
        "repository": repository,
        "branches": [
            {"name": "node-73-final-acceptance-release", "protected": True, "head_sha": "b" * 40, "protection": profile},
            {"name": "release-closure-p0", "protected": True, "head_sha": release_sha, "protection": profile},
        ],
    }
    clean = validate_report(good, expected_repository=repository, expected_release_sha=release_sha)

    bad_reports: list[dict[str, Any]] = []
    bad_reports.append({**good, "status": "BLOCKED_EXTERNAL"})
    bad_reports.append({**good, "repository": "example/other"})
    bad_reports.append({**good, "branches": [{**good["branches"][0], "protected": False}, good["branches"][1]]})
    bad_reports.append({**good, "branches": [good["branches"][0], {**good["branches"][1], "head_sha": "c" * 40}]})
    for key, unsafe in (
        ("enforce_admins", False),
        ("required_linear_history", False),
        ("required_conversation_resolution", False),
        ("allow_force_pushes", True),
        ("allow_deletions", True),
    ):
        mutated = dict(profile)
        mutated[key] = unsafe
        bad_reports.append({**good, "branches": [{**good["branches"][0], "protection": mutated}, good["branches"][1]]})
    reviews = dict(profile["required_pull_request_reviews"])
    reviews["require_last_push_approval"] = False
    mutated = dict(profile)
    mutated["required_pull_request_reviews"] = reviews
    bad_reports.append({**good, "branches": [{**good["branches"][0], "protection": mutated}, good["branches"][1]]})
    checks = dict(profile["required_status_checks"])
    checks["contexts"] = []
    checks["count"] = 0
    mutated = dict(profile)
    mutated["required_status_checks"] = checks
    bad_reports.append({**good, "branches": [{**good["branches"][0], "protection": mutated}, good["branches"][1]]})

    blocked = 0
    for index, report in enumerate(bad_reports, start=1):
        try:
            validate_report(report, expected_repository=repository, expected_release_sha=release_sha)
        except BranchProtectionError:
            blocked += 1
            continue
        raise BranchProtectionError(f"negative branch protection drill did not block: {index}")
    return {"status": "PASS", "clean": clean, "negative_drills": blocked}


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture and validate NODE-73 strong release branch protection evidence")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--expected-release-sha")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    report = capture(
        args.repository,
        token=os.environ.get("RELEASE_GOVERNANCE_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN"),
    )
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if report["status"] != "PASS":
        raise BranchProtectionError("required NODE-73 release branches are not strongly protected")
    validate_report(
        report,
        expected_repository=args.repository,
        expected_release_sha=args.expected_release_sha,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BranchProtectionError as exc:
        raise SystemExit(f"release branch protection blocked: {exc}") from exc

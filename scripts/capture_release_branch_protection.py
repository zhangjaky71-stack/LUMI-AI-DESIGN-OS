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


class BranchProtectionError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BranchProtectionError(message)


def validate_branch_payload(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    _require(name in REQUIRED_BRANCHES, f"unexpected release branch: {name}")
    _require(payload.get("name") == name, f"GitHub branch response name mismatch for {name}")
    protected = payload.get("protected")
    _require(isinstance(protected, bool), f"GitHub branch protected flag missing for {name}")
    commit = payload.get("commit")
    _require(isinstance(commit, Mapping), f"GitHub branch commit missing for {name}")
    sha = commit.get("sha")
    _require(isinstance(sha, str) and bool(SHA40.fullmatch(sha.lower())), f"GitHub branch head SHA invalid for {name}")
    return {
        "name": name,
        "protected": protected,
        "head_sha": sha.lower(),
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
    }


def _fetch_branch(repository: str, branch: str, *, token: str | None) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repository}/branches/{branch}"
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
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BranchProtectionError(f"GitHub branch lookup failed for {branch}: {exc}") from exc
    _require(isinstance(payload, dict), f"GitHub branch lookup returned non-object for {branch}")
    return payload


def capture(repository: str, *, token: str | None) -> dict[str, Any]:
    _require(bool(REPOSITORY.fullmatch(repository)), "repository must use OWNER/REPO form")
    branches = [
        validate_branch_payload(name, _fetch_branch(repository, name, token=token))
        for name in REQUIRED_BRANCHES
    ]
    all_protected = all(item["protected"] is True for item in branches)
    return {
        "schema_version": 1,
        "kind": KIND,
        "status": "PASS" if all_protected else "BLOCKED_EXTERNAL",
        "repository": repository,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "branches": branches,
    }


def self_test() -> dict[str, Any]:
    repository = "example/lumi"
    release_sha = "a" * 40
    good = {
        "schema_version": 1,
        "kind": KIND,
        "status": "PASS",
        "repository": repository,
        "branches": [
            {"name": "node-73-final-acceptance-release", "protected": True, "head_sha": "b" * 40},
            {"name": "release-closure-p0", "protected": True, "head_sha": release_sha},
        ],
    }
    clean = validate_report(good, expected_repository=repository, expected_release_sha=release_sha)

    drills = []
    bad_reports = [
        {**good, "status": "BLOCKED_EXTERNAL"},
        {**good, "repository": "example/other"},
        {**good, "branches": [{**good["branches"][0], "protected": False}, good["branches"][1]]},
        {**good, "branches": [good["branches"][0], {**good["branches"][1], "head_sha": "c" * 40}]},
    ]
    for index, report in enumerate(bad_reports, start=1):
        try:
            validate_report(report, expected_repository=repository, expected_release_sha=release_sha)
        except BranchProtectionError:
            drills.append(index)
            continue
        raise BranchProtectionError(f"negative branch protection drill did not block: {index}")
    return {"status": "PASS", "clean": clean, "negative_drills": len(drills)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture and validate NODE-73 release branch protection evidence")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    report = capture(args.repository, token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if report["status"] != "PASS":
        raise BranchProtectionError("required NODE-73 release branches are not protected")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BranchProtectionError as exc:
        raise SystemExit(f"release branch protection blocked: {exc}") from exc

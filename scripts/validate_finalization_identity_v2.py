#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
EXPECTED_REF = "refs/heads/release-closure-p0"
EXPECTED_WORKFLOW = (
    "zhangjaky71-stack/LUMI-AI-DESIGN-OS/"
    ".github/workflows/final-acceptance-gate.yml@refs/heads/release-closure-p0"
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class FinalizationIdentityError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalizationIdentityError(message)


def normalize_sha(value: object, *, label: str) -> str:
    require(isinstance(value, str) and bool(SHA40.fullmatch(value.lower())), f"{label} must be exact SHA40")
    return value.lower()


def validate_identity(
    *,
    source_rc_sha: str,
    evidence_head_sha: str,
    execution_sha: str,
    repository: str,
    ref: str,
    workflow_ref: str,
    pr_head_sha: str,
    live_branch_head_sha: str,
    source_is_ancestor: bool,
) -> dict[str, Any]:
    source = normalize_sha(source_rc_sha, label="source_rc_sha")
    evidence = normalize_sha(evidence_head_sha, label="evidence_head_sha")
    execution = normalize_sha(execution_sha, label="execution_sha")
    pr_head = normalize_sha(pr_head_sha, label="pr_head_sha")
    live_head = normalize_sha(live_branch_head_sha, label="live_branch_head_sha")

    require(repository == EXPECTED_REPOSITORY, "repository identity mismatch")
    require(ref == EXPECTED_REF, "Final Decision ref must be release-closure-p0")
    require(workflow_ref == EXPECTED_WORKFLOW, "Final Decision workflow ref mismatch")
    require(execution == evidence, "workflow execution SHA must equal Evidence Head SHA")
    require(pr_head == evidence, "PR #135 head SHA must equal Evidence Head SHA")
    require(live_head == evidence, "live protected release branch head must equal Evidence Head SHA")
    require(source_is_ancestor is True, "Source RC SHA must be an ancestor of Evidence Head SHA")

    return {
        "schema_version": 1,
        "kind": "LUMI_FINALIZATION_IDENTITY_V2",
        "status": "PASS",
        "repository": EXPECTED_REPOSITORY,
        "source_rc_sha": source,
        "evidence_head_sha": evidence,
        "execution_sha": execution,
        "ref": ref,
        "workflow_ref": workflow_ref,
        "pr_head_sha": pr_head,
        "live_branch_head_sha": live_head,
        "source_rc_ancestor_of_evidence_head": True,
        "source_and_evidence_may_differ": source != evidence,
    }


def git_is_ancestor(source_rc_sha: str, evidence_head_sha: str) -> bool:
    source = normalize_sha(source_rc_sha, label="source_rc_sha")
    evidence = normalize_sha(evidence_head_sha, label="evidence_head_sha")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source, evidence],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise FinalizationIdentityError("git merge-base could not evaluate Source RC ancestry")


def from_environment(
    *,
    source_rc_sha: str,
    pr_head_sha: str,
    live_branch_head_sha: str,
) -> dict[str, Any]:
    evidence = normalize_sha(os.environ.get("GITHUB_SHA", ""), label="GITHUB_SHA/evidence_head_sha")
    return validate_identity(
        source_rc_sha=source_rc_sha,
        evidence_head_sha=evidence,
        execution_sha=evidence,
        repository=os.environ.get("GITHUB_REPOSITORY", ""),
        ref=os.environ.get("GITHUB_REF", ""),
        workflow_ref=os.environ.get("GITHUB_WORKFLOW_REF", ""),
        pr_head_sha=pr_head_sha,
        live_branch_head_sha=live_branch_head_sha,
        source_is_ancestor=git_is_ancestor(source_rc_sha, evidence),
    )


def self_test() -> dict[str, Any]:
    source = "a" * 40
    evidence = "b" * 40
    base = {
        "source_rc_sha": source,
        "evidence_head_sha": evidence,
        "execution_sha": evidence,
        "repository": EXPECTED_REPOSITORY,
        "ref": EXPECTED_REF,
        "workflow_ref": EXPECTED_WORKFLOW,
        "pr_head_sha": evidence,
        "live_branch_head_sha": evidence,
        "source_is_ancestor": True,
    }
    clean = validate_identity(**base)
    require(clean["source_and_evidence_may_differ"] is True, "clean V2 fixture must prove distinct Source RC/Evidence Head is valid")

    mutations = [
        {**base, "execution_sha": "c" * 40},
        {**base, "pr_head_sha": "c" * 40},
        {**base, "live_branch_head_sha": "c" * 40},
        {**base, "repository": "example/other"},
        {**base, "ref": "refs/heads/other"},
        {**base, "workflow_ref": "example/other/.github/workflows/x.yml@refs/heads/main"},
        {**base, "source_is_ancestor": False},
    ]
    blocked = 0
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate_identity(**mutation)
        except FinalizationIdentityError:
            blocked += 1
            continue
        raise FinalizationIdentityError(f"negative V2 finalization identity drill did not block: {index}")
    return {"status": "PASS", "clean": clean, "negative_drills": blocked}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate NODE-73 non-cyclic Source RC / Evidence Head identity")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source-rc-sha")
    parser.add_argument("--pr-head-sha")
    parser.add_argument("--live-branch-head-sha")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    require(args.source_rc_sha is not None, "--source-rc-sha is required")
    require(args.pr_head_sha is not None, "--pr-head-sha is required")
    require(args.live_branch_head_sha is not None, "--live-branch-head-sha is required")
    print(
        json.dumps(
            from_environment(
                source_rc_sha=args.source_rc_sha,
                pr_head_sha=args.pr_head_sha,
                live_branch_head_sha=args.live_branch_head_sha,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FinalizationIdentityError, OSError) as exc:
        raise SystemExit(f"finalization identity V2 blocked: {exc}") from exc

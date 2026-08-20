#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
EXPECTED_WORKFLOW = "Database Schema"
EXPECTED_WORKFLOW_PATH = ".github/workflows/database-schema.yml"
KIND = "LUMI_DATABASE_SCHEMA_SOURCE_INTEGRATION_V1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
REVISION = re.compile(r"^[A-Za-z0-9_.-]+$")
REQUIRED_CHECKS = (
    "frozen_workspace_sync",
    "empty_database_upgrade_to_head",
    "orm_migration_drift_check",
    "deterministic_seed",
    "current_revision_check",
    "downgrade_reupgrade_smoke",
    "post_downgrade_drift_check",
    "persistence_integration_tests",
)


class DatabaseEvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DatabaseEvidenceError(message)


def normalize_sha(value: object, *, label: str) -> str:
    require(isinstance(value, str) and bool(SHA40.fullmatch(value.lower())), f"{label} must be exact SHA40")
    return value.lower()


def revision(value: object, *, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{label} is missing")
    text = value.strip()
    require(bool(REVISION.fullmatch(text)), f"{label} has invalid format")
    return text


def build_payload(
    *,
    repository: str,
    git_sha: str,
    migration_head: str,
    current_revision: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
    workflow_path: str,
    run_url: str,
) -> dict[str, Any]:
    require(repository == EXPECTED_REPOSITORY, "database evidence repository mismatch")
    source_sha = normalize_sha(git_sha, label="database evidence git_sha")
    head = revision(migration_head, label="migration_head")
    current = revision(current_revision, label="current_revision")
    require(current == head, "database current revision must equal canonical migration head")
    require(run_id.isdecimal() and int(run_id) > 0, "database evidence run_id must be positive decimal")
    require(run_attempt.isdecimal() and int(run_attempt) > 0, "database evidence run_attempt must be positive decimal")
    require(workflow == EXPECTED_WORKFLOW, "database evidence workflow name mismatch")
    require(workflow_path == EXPECTED_WORKFLOW_PATH, "database evidence workflow path mismatch")
    expected_url = f"https://github.com/{EXPECTED_REPOSITORY}/actions/runs/{run_id}"
    require(run_url == expected_url, "database evidence run URL mismatch")
    return {
        "schema_version": 1,
        "kind": KIND,
        "status": "PASS",
        "repository": EXPECTED_REPOSITORY,
        "git_sha": source_sha,
        "migration_head": head,
        "current_revision": current,
        "checks": {name: "PASS" for name in REQUIRED_CHECKS},
        "producer": {
            "workflow": EXPECTED_WORKFLOW,
            "workflow_path": EXPECTED_WORKFLOW_PATH,
            "run_id": int(run_id),
            "run_attempt": int(run_attempt),
            "run_url": expected_url,
        },
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def from_environment(*, migration_head: str, current_revision: str) -> dict[str, Any]:
    return build_payload(
        repository=os.environ.get("GITHUB_REPOSITORY", ""),
        git_sha=os.environ.get("GITHUB_SHA", ""),
        migration_head=migration_head,
        current_revision=current_revision,
        run_id=os.environ.get("GITHUB_RUN_ID", ""),
        run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        workflow=os.environ.get("GITHUB_WORKFLOW", ""),
        workflow_path=EXPECTED_WORKFLOW_PATH,
        run_url=(
            f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/"
            f"{os.environ.get('GITHUB_RUN_ID', '')}"
        ),
    )


def self_test() -> dict[str, Any]:
    clean = build_payload(
        repository=EXPECTED_REPOSITORY,
        git_sha="a" * 40,
        migration_head="0021_tool_approval_scope",
        current_revision="0021_tool_approval_scope",
        run_id="123",
        run_attempt="1",
        workflow=EXPECTED_WORKFLOW,
        workflow_path=EXPECTED_WORKFLOW_PATH,
        run_url=f"https://github.com/{EXPECTED_REPOSITORY}/actions/runs/123",
    )
    require(clean["status"] == "PASS", "clean database evidence fixture did not PASS")
    require(set(clean["checks"]) == set(REQUIRED_CHECKS), "database evidence check set drift")

    blocked = 0
    drills = [
        dict(repository="example/other"),
        dict(git_sha="bad"),
        dict(migration_head="0021", current_revision="0020"),
        dict(run_id="0"),
        dict(run_attempt="0"),
        dict(workflow="Other"),
        dict(workflow_path=".github/workflows/other.yml"),
        dict(run_url=f"https://github.com/{EXPECTED_REPOSITORY}/actions/runs/999"),
    ]
    base = {
        "repository": EXPECTED_REPOSITORY,
        "git_sha": "a" * 40,
        "migration_head": "0021_tool_approval_scope",
        "current_revision": "0021_tool_approval_scope",
        "run_id": "123",
        "run_attempt": "1",
        "workflow": EXPECTED_WORKFLOW,
        "workflow_path": EXPECTED_WORKFLOW_PATH,
        "run_url": f"https://github.com/{EXPECTED_REPOSITORY}/actions/runs/123",
    }
    for index, overrides in enumerate(drills, start=1):
        args = dict(base)
        args.update(overrides)
        try:
            build_payload(**args)
        except DatabaseEvidenceError:
            blocked += 1
            continue
        raise DatabaseEvidenceError(f"negative database evidence drill did not block: {index}")
    return {"status": "PASS", "negative_drills": blocked, "required_checks": len(REQUIRED_CHECKS)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture trusted source-level PostgreSQL migration/integration evidence")
    parser.add_argument("--migration-head")
    parser.add_argument("--current-revision")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            payload = self_test()
        else:
            require(isinstance(args.migration_head, str), "--migration-head is required")
            require(isinstance(args.current_revision, str), "--current-revision is required")
            require(args.output is not None, "--output is required")
            payload = from_environment(
                migration_head=args.migration_head,
                current_revision=args.current_revision,
            )
            output = args.output.resolve()
            allowed = (ROOT / "reports" / "database").resolve()
            try:
                output.relative_to(allowed)
            except ValueError as exc:
                raise DatabaseEvidenceError("database evidence output must stay below reports/database/") from exc
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except DatabaseEvidenceError as exc:
        raise SystemExit(f"database source integration evidence blocked: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())

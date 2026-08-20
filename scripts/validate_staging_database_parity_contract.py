#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "apps/api/src/lumi_api/staging_database_parity_probe.py"
VALIDATOR = ROOT / "scripts/validate_staging_database_parity_evidence.py"
FREEZER = ROOT / "scripts/freeze_staging_evidence_artifact.py"
COLLECTOR = ROOT / ".github/workflows/collect-staging-database-parity.yml"
FREEZE = ROOT / ".github/workflows/freeze-staging-database-parity.yml"
SHA40 = "a" * 40


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def require_pinned_actions(text: str, label: str) -> None:
    uses = re.findall(r"^\s*-\s+uses:\s+([^\s#]+)", text, flags=re.MULTILINE)
    require(bool(uses), f"{label} has no external actions")
    for item in uses:
        require(re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", item) is not None, f"{label} action is not immutable SHA pinned: {item}")


def validate_probe() -> None:
    text = PROBE.read_text(encoding="utf-8")
    for marker in (
        'MIGRATION_DATABASE_URL',
        '["alembic", "-c", "apps/api/alembic.ini", "check"]',
        'SET TRANSACTION READ ONLY',
        'SHOW transaction_read_only',
        'SHOW server_version_num',
        'SELECT version_num FROM alembic_version ORDER BY version_num',
        'LUMI_ENV must equal staging',
        'migration secret does not target canonical Staging PostgreSQL host',
        'LUMI_STAGING_DB_PARITY=',
    ):
        require(marker in text, f"database parity probe missing marker: {marker}")
    require('"upgrade", "head"' not in text, "database parity probe must never execute Alembic upgrade")
    require("boto3" not in text and "put_object" not in text, "database parity probe must not acquire evidence-storage write capability")


def validate_validator_and_freezer() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--self-test"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, "database parity evidence validator self-test failed")
    payload = json.loads(result.stdout)
    require(payload == {"negative_drills": 8, "status": "PASS"}, "database parity evidence negative drill contract drifted")

    freezer = load_module(FREEZER, "lumi_staging_evidence_freezer")
    source_run = {
        "repository": "zhangjaky71-stack/LUMI-AI-DESIGN-OS",
        "id": 123,
        "name": "Collect Staging Database Parity",
        "path": ".github/workflows/collect-staging-database-parity.yml",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "html_url": "https://github.com/zhangjaky71-stack/LUMI-AI-DESIGN-OS/actions/runs/123",
        "head_sha": "b" * 40,
        "head_branch": "release-closure-p0",
        "updated_at": "2026-08-20T00:00:00Z",
    }
    validation = {"status": "PASS", "release_git_sha": SHA40}
    raw = {"release_candidate": {"git_sha": SHA40}}
    wrapper = freezer.freeze(
        artifact_id=f"staging-database-parity:{SHA40}",
        rc_sha=SHA40,
        validation=validation,
        source_run=source_run,
        raw_evidence=raw,
        raw_evidence_sha256="c" * 64,
    )
    require(wrapper.get("status") == "PASS" and wrapper.get("rc_git_sha") == SHA40, "generic freezer clean fixture failed")
    require(wrapper.get("producer", {}).get("workflow_path") == ".github/workflows/collect-staging-database-parity.yml", "generic freezer lost producer workflow path")
    bad = dict(source_run)
    bad["conclusion"] = "failure"
    try:
        freezer.freeze(
            artifact_id=f"staging-database-parity:{SHA40}",
            rc_sha=SHA40,
            validation=validation,
            source_run=bad,
            raw_evidence=raw,
            raw_evidence_sha256="c" * 64,
        )
    except Exception:
        pass
    else:
        raise ContractError("generic freezer accepted a failed collector run")


def validate_collector() -> None:
    text = COLLECTOR.read_text(encoding="utf-8")
    require_pinned_actions(text, "database parity collector")
    for marker in (
        "permissions:\n  contents: read\n  id-token: write",
        "environment: staging",
        'ref: ${{ inputs.release_git_sha }}',
        "persist-credentials: false",
        'test "$(git rev-parse HEAD)" = "$RELEASE_GIT_SHA"',
        'EXPECTED_API_IMAGE: ${{ vars.API_IMAGE_DIGEST }}',
        'EXPECTED_POSTGRES_ENGINE_VERSION: ${{ vars.POSTGRES_ENGINE_VERSION }}',
        'EXPECTED_ACCOUNT_ID: ${{ vars.AWS_ACCOUNT_ID }}',
        'lumi/staging/core/terraform.tfstate',
        'lumi/staging/migration/terraform.tfstate',
        'terraform -chdir=infra/iac/environments/staging/migration output -raw migration_task_definition_arn',
        'terraform -chdir=infra/iac/environments/staging/core output -raw postgres_endpoint',
        'test "$migration_image" = "$EXPECTED_API_IMAGE"',
        'test "$api_image" = "$migration_image"',
        'assignPublicIp=DISABLED',
        '"lumi_api.staging_database_parity_probe"',
        '^LUMI_STAGING_DB_PARITY=',
        'validate_staging_database_parity_evidence.py --self-test',
        '--expected-git-sha "$RELEASE_GIT_SHA"',
        '--expected-postgres-major "$EXPECTED_POSTGRES_MAJOR"',
        '--expected-host-sha256 "$DATABASE_HOST_SHA256"',
        'staging-database-parity-${{ github.run_id }}-${{ github.run_attempt }}',
    ):
        require(marker in text, f"database parity collector missing marker: {marker}")
    require("contents: write" not in text, "database parity collector must never receive contents:write")
    require("assignPublicIp=ENABLED" not in text, "database parity collector must never launch probe with public IP")


def validate_freeze_workflow() -> None:
    text = FREEZE.read_text(encoding="utf-8")
    require_pinned_actions(text, "database parity freeze")
    for marker in (
        "permissions:\n  contents: read",
        "validate-freeze:",
        "contents: read\n      actions: read",
        "commit-freeze:",
        "contents: write",
        'test "$GITHUB_REF_NAME" = "release-closure-p0"',
        'test "$(jq -r \'.name\' <<<"$run")" = "Collect Staging Database Parity"',
        'test "$(jq -r \'.path\' <<<"$run")" = ".github/workflows/collect-staging-database-parity.yml"',
        'test "$(jq -r \'.conclusion\' <<<"$run")" = "success"',
        'git merge-base --is-ancestor "$RC_SHA" "$collector_head"',
        'git merge-base --is-ancestor "$collector_head" "$GITHUB_SHA"',
        'scripts/freeze_staging_evidence_artifact.py',
        'STAGING_EVIDENCE_GITHUB_TOKEN="$GH_TOKEN" python3 scripts/validate_staging_evidence_artifacts.py',
        '--require-live-producers',
        'reports/staging-acceptance/evidence/${RC_SHA}',
        'remote="$(git ls-remote',
        'test "$remote" = "$expected"',
        'git add -- "$target/database-parity.json" "$target/database-parity.catalog.json"',
        'HEAD:release-closure-p0',
    ):
        require(marker in text, f"database parity freeze missing marker: {marker}")
    require("--force" not in text and "git push -f" not in text, "database parity freeze must never force push")
    commit = text[text.index("  commit-freeze:\n") :]
    for forbidden in (
        "validate_staging_database_parity_evidence.py",
        "freeze_staging_evidence_artifact.py",
        "validate_staging_evidence_artifacts.py",
        "terraform ",
        "aws ecs",
        "aws logs",
    ):
        require(forbidden not in commit, f"write-capable freeze job must not execute project/runtime logic: {forbidden}")
    require(text.count('GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}') == 1, "write token must be explicitly injected exactly once")


def main() -> int:
    for path in (PROBE, VALIDATOR, FREEZER, COLLECTOR, FREEZE):
        require(path.is_file(), f"required database parity producer source is missing: {path.relative_to(ROOT)}")
    validate_probe()
    validate_validator_and_freezer()
    validate_collector()
    validate_freeze_workflow()
    print(json.dumps({"status": "PASS", "database_parity_negative_drills": 8, "collector_private_fargate": True, "freeze_two_phase": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"staging database parity producer contract failed: {exc}") from exc

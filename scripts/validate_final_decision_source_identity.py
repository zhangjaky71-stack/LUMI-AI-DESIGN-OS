#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "scripts" / "final-acceptance-decision.py"
WORKFLOW = ROOT / ".github" / "workflows" / "final-acceptance-gate.yml"


class SourceIdentityError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceIdentityError(message)


def job_block(text: str, job: str, next_job: str | None) -> str:
    marker = f"  {job}:\n"
    start = text.find(marker)
    if start < 0:
        raise SourceIdentityError(f"missing workflow job: {job}")
    if next_job is None:
        return text[start:]
    end = text.find(f"  {next_job}:\n", start + len(marker))
    if end < 0:
        raise SourceIdentityError(f"missing workflow job terminator: {next_job}")
    return text[start:end]


def main() -> int:
    decision = DECISION.read_text(encoding="utf-8")
    for marker in (
        'EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"',
        'EXPECTED_RELEASE_REF = "refs/heads/release-closure-p0"',
        'EXPECTED_WORKFLOW_PATH = ".github/workflows/final-acceptance-gate.yml"',
        'def validate_execution_identity(*, rc_sha: str)',
        'repository = os.environ.get("GITHUB_REPOSITORY", "")',
        'ref = os.environ.get("GITHUB_REF", "")',
        'sha = os.environ.get("GITHUB_SHA", "").lower()',
        'workflow_ref = os.environ.get("GITHUB_WORKFLOW_REF", "")',
        'run_id = os.environ.get("GITHUB_RUN_ID", "")',
        'repository != EXPECTED_REPOSITORY',
        'ref != EXPECTED_RELEASE_REF',
        'sha != rc_sha.lower()',
        'workflow_ref != expected_workflow_ref',
        'not run_id.isdecimal()',
        'execution_identity = validate_execution_identity(rc_sha=rc_sha)',
        '"execution_identity": execution_identity',
        '"run_url": f"https://github.com/{repository}/actions/runs/{run_id}"',
    ):
        require(marker in decision, f"Final Decision wrapper missing execution identity marker: {marker}")

    rc_pos = decision.find('rc_sha = rc["git_sha"].lower()')
    identity_pos = decision.find("execution_identity = validate_execution_identity(rc_sha=rc_sha)")
    governance_pos = decision.find("governance.capture(EXPECTED_REPOSITORY, token=governance_token)")
    product_pos = decision.find("product_gate.evaluate(matrix, release, evidence, evidence_path)")
    bind_pos = decision.find('"execution_identity": execution_identity')
    require(
        min(rc_pos, identity_pos, governance_pos, product_pos, bind_pos) >= 0
        and rc_pos < identity_pos < governance_pos < product_pos < bind_pos,
        "execution identity must be validated immediately after RC resolution and bound into final decision",
    )

    workflow = WORKFLOW.read_text(encoding="utf-8")
    final = job_block(workflow, "final-decision", "contract-gate")
    for marker in (
        "github.event_name == 'workflow_dispatch'",
        "github.ref_type == 'branch'",
        "github.ref_name == 'release-closure-p0'",
        "ref: ${{ github.sha }}",
        "fetch-depth: 0",
        "name: Require exact immutable Final Decision source revision",
        'test "$GITHUB_REF_TYPE" = "branch"',
        'test "$GITHUB_REF_NAME" = "release-closure-p0"',
        'test "$GITHUB_REF" = "refs/heads/release-closure-p0"',
        'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
        'test -z "$(git status --porcelain)"',
        "python3 scripts/final-acceptance-decision.py",
    ):
        require(marker in final, f"Final Acceptance workflow missing source identity marker: {marker}")

    require(
        "ref: ${{ github.ref_name }}" not in final,
        "Final Decision checkout must never re-resolve the movable branch name after dispatch",
    )

    print("NODE-73 Final Decision execution source identity contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SourceIdentityError, OSError) as exc:
        raise SystemExit(f"final decision source identity contract failed: {exc}") from exc

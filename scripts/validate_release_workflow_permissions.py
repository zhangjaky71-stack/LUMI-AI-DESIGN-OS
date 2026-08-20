#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSEMBLE = ROOT / ".github/workflows/assemble-final-acceptance.yml"
BUILD = ROOT / ".github/workflows/build-runtime-image-set.yml"
GOVERNANCE_APPLY = ROOT / ".github/workflows/configure-release-branch-protection.yml"
LOCK = ROOT / ".github/workflows/regenerate-uv-lock.yml"
RUNTIME = ROOT / ".github/workflows/runtime-image-closure-contract.yml"
STAGING = ROOT / ".github/workflows/staging-acceptance-gate.yml"
PROD_IAC = ROOT / ".github/workflows/production-iac-contract.yml"
DEPLOY = ROOT / ".github/workflows/deploy-production.yml"
FINAL = ROOT / ".github/workflows/final-acceptance-gate.yml"


class PermissionContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PermissionContractError(message)


def text(path: Path) -> str:
    require(path.is_file(), f"missing release workflow: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def top(source: str) -> str:
    end = source.find("jobs:\n")
    require(end >= 0, "workflow has no jobs section")
    return source[:end]


def job_block(source: str, job: str, next_job: str | None) -> str:
    marker = f"  {job}:\n"
    start = source.find(marker)
    require(start >= 0, f"missing workflow job: {job}")
    if next_job is None:
        return source[start:]
    end = source.find(f"  {next_job}:\n", start + len(marker))
    require(end >= 0, f"missing workflow job terminator: {next_job}")
    return source[start:end]


def require_top_read_only(source: str, label: str) -> None:
    header = top(source)
    require("permissions:\n  contents: read\n" in header, f"{label} must default to contents:read")
    for forbidden in (
        "contents: write",
        "actions: write",
        "packages: write",
        "attestations: write",
        "id-token: write",
        "pull-requests: write",
    ):
        require(forbidden not in header, f"{label} top-level permission too broad: {forbidden}")


def validate_assemble() -> None:
    source = text(ASSEMBLE)
    require_top_read_only(source, "Final Acceptance package assembler")
    assemble = job_block(source, "assemble", None)
    require("permissions:\n      contents: write\n" in assemble, "only Final Acceptance assembler may receive contents:write")
    for forbidden in ("actions: write", "packages: write", "attestations: write", "id-token: write", "pull-requests: write"):
        require(forbidden not in assemble, f"Final Acceptance assembler has unrelated write capability: {forbidden}")
    require("github.ref == 'refs/heads/release-closure-p0'" in assemble, "Final Acceptance assembler must be release-closure-p0-only")
    require('ref: ${{ github.sha }}' in assemble and "fetch-depth: 0" in assemble, "Final Acceptance assembler must checkout exact dispatch SHA with full history")
    require('git push origin "HEAD:${GITHUB_REF_NAME}"' in assemble, "Final Acceptance assembler must push only the current release branch")
    require("git push --force" not in assemble.casefold(), "Final Acceptance assembler must never force-push")
    require('test "$remote_sha" = "$GITHUB_SHA"' in assemble, "Final Acceptance assembler must fail closed if release branch moves")
    require("final-acceptance-assembler-v2.py" in assemble and "final-acceptance-assembler.py" not in assemble, "Final Acceptance assembler must be V2-only")


def validate_governance_apply() -> None:
    source = text(GOVERNANCE_APPLY)
    require_top_read_only(source, "NODE-73 branch-protection workflow")
    header = top(source)
    require("workflow_dispatch:" in header, "branch-protection workflow must retain manual mutation dispatch")
    require("pull_request:\n    types: [labeled]" in header, "branch-protection workflow must retain unprivileged PR preflight")

    preflight = job_block(source, "pr-preflight", "apply-protection")
    apply_job = job_block(source, "apply-protection", None)

    for marker in (
        "github.event_name == 'pull_request'",
        "github.event.label.name == 'node73-protection-preflight'",
        "github.event.pull_request.number == 135",
        "github.event.pull_request.base.ref == 'node-73-final-acceptance-release'",
        "github.event.pull_request.head.ref == 'release-closure-p0'",
        "github.event.pull_request.head.repo.full_name == github.repository",
        'EVIDENCE_HEAD_SHA: ${{ github.event.pull_request.head.sha }}',
        'ref: ${{ env.EVIDENCE_HEAD_SHA }}',
        'test "$(git rev-parse HEAD)" = "$EVIDENCE_HEAD_SHA"',
        "persist-credentials: false",
        "PR preflight only: no Administration credential is available to PR-controlled code.",
    ):
        require(marker in preflight, f"PR governance preflight missing constraint: {marker}")
    require("environment: production" not in preflight, "PR-controlled preflight must not cross the production secret boundary")
    require("RELEASE_GOVERNANCE_ADMIN_TOKEN" not in preflight, "Administration-write token must never enter PR-controlled preflight")
    for forbidden in ("contents: write", "actions: write", "packages: write", "attestations: write", "id-token: write", "pull-requests: write"):
        require(forbidden not in preflight, f"PR governance preflight has write capability: {forbidden}")

    for marker in (
        "github.event_name == 'workflow_dispatch'",
        "github.ref == 'refs/heads/release-closure-p0'",
        "inputs.confirm == 'APPLY_NODE73_RELEASE_PROTECTION'",
        "environment: production",
        'EVIDENCE_HEAD_SHA: ${{ github.sha }}',
        'ref: ${{ env.EVIDENCE_HEAD_SHA }}',
        'test "$(git rev-parse HEAD)" = "$EVIDENCE_HEAD_SHA"',
        "persist-credentials: false",
        'RELEASE_GOVERNANCE_ADMIN_TOKEN: ${{ secrets.RELEASE_GOVERNANCE_ADMIN_TOKEN }}',
        "apply_release_branch_protection.py",
    ):
        require(marker in apply_job, f"privileged governance mutation missing constraint: {marker}")
    require("github.event_name == 'pull_request'" not in apply_job, "Administration-write mutation job must not accept pull_request events")
    require("permissions:\n      contents: read\n" in apply_job, "governance mutation must not receive repository write via GITHUB_TOKEN")
    for forbidden in ("contents: write", "actions: write", "packages: write", "attestations: write", "id-token: write", "pull-requests: write"):
        require(forbidden not in apply_job, f"governance mutation has unrelated GitHub permission: {forbidden}")
    require(source.count("${{ secrets.RELEASE_GOVERNANCE_ADMIN_TOKEN }}") == 1, "Administration-write token must be injected into exactly one step")
    require("RELEASE_GOVERNANCE_ADMIN_TOKEN:" not in header, "Administration-write token must never be workflow-scoped")


def validate_build() -> None:
    source = text(BUILD)
    require_top_read_only(source, "runtime image build")
    read_gate = job_block(source, "source-gate", "build-and-freeze")
    write_job = job_block(source, "build-and-freeze", None)
    require("permissions:\n      contents: read\n" in read_gate, "runtime image source-gate must explicitly be read-only")
    for forbidden in ("contents: write", "actions: write", "packages: write", "attestations: write", "id-token: write"):
        require(forbidden not in read_gate, f"runtime image source-gate has write capability: {forbidden}")
    require("needs: [source-gate]" in write_job, "runtime image write job must depend on read-only source-gate")
    for required in ("contents: read", "packages: write", "attestations: write", "id-token: write"):
        require(required in write_job, f"runtime image build job missing scoped permission: {required}")
    require("actions: write" not in write_job and "contents: write" not in write_job, "runtime image build job has unnecessary repository write permission")
    require("docker/login-action@" not in read_gate and "docker/build-push-action@" not in read_gate and "actions/attest@" not in read_gate, "read-only image source gate must not mutate registry/attestations")


def validate_lock() -> None:
    source = text(LOCK)
    require_top_read_only(source, "NODE-73 canonical uv-lock regeneration")
    header = top(source)
    require("workflow_dispatch:" in header, "uv-lock workflow must be manual-dispatch only")
    require("REGENERATE_NODE73_UV_LOCK" in header, "uv-lock workflow must require typed confirmation")
    require("expected_sha:" in header, "uv-lock workflow must require exact target SHA")

    regenerate = job_block(source, "regenerate-lock", "commit-lock")
    commit = job_block(source, "commit-lock", None)

    require("permissions:\n      contents: read\n" in regenerate, "uv resolver phase must be read-only")
    for forbidden in ("contents: write", "actions: write", "packages: write", "attestations: write", "id-token: write", "pull-requests: write"):
        require(forbidden not in regenerate, f"uv resolver phase has write capability: {forbidden}")
    require("GITHUB_TOKEN" not in regenerate, "uv resolver/project-code phase must not receive GitHub write token")
    require("uv lock" in regenerate and "uv sync --all-packages --frozen" in regenerate, "read-only phase must perform canonical resolver/frozen sync")
    require("actions/upload-artifact@" in regenerate, "read-only phase must freeze regenerated uv.lock as a same-run artifact")

    require("needs: [regenerate-lock]" in commit, "uv-lock commit phase must depend on successful resolver phase")
    require("needs.regenerate-lock.outputs.changed == 'true'" in commit, "uv-lock commit phase must skip idempotent no-change runs")
    require("permissions:\n      contents: write\n" in commit, "only uv-lock commit phase may receive contents:write")
    for forbidden in ("actions: write", "packages: write", "attestations: write", "id-token: write", "pull-requests: write"):
        require(forbidden not in commit, f"uv-lock commit phase has unrelated capability: {forbidden}")
    require("actions/download-artifact@" in commit, "uv-lock commit phase must consume the exact same-run artifact")
    require("uv lock" not in commit and "uv sync" not in commit, "write-capable uv-lock phase must never resolve/install project dependencies")
    require("python3 scripts/" not in commit, "write-capable uv-lock phase must not execute release-branch Python scripts")
    require(commit.count("GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}") == 1, "uv-lock write token must be injected into exactly one fixed mutation step")
    require("git add -- uv.lock" in commit and "git push --force" not in commit.casefold(), "uv-lock mutation must remain narrow and non-force")
    require('test "$(git rev-parse "origin/${TARGET_REF}")" = "$EXPECTED_SHA"' in commit, "uv-lock mutation must fail closed if release branch moved")


def validate_staging() -> None:
    source = text(STAGING)
    require_top_read_only(source, "NODE-71 staging acceptance")
    source_contract = job_block(source, "source-contract", "canonical-lock-gate")
    lock_gate = job_block(source, "canonical-lock-gate", "remote-read-only-preflight")
    preflight = job_block(source, "remote-read-only-preflight", "acceptance-decision")
    decision = job_block(source, "acceptance-decision", "contract-gate")
    for label, block in (("source-contract", source_contract), ("canonical-lock-gate", lock_gate), ("remote-read-only-preflight", preflight)):
        require("actions: read" not in block, f"NODE-71 {label} must not receive cross-run artifact read permission")
    require("permissions:\n      contents: read\n      actions: read\n" in decision, "only NODE-71 acceptance-decision may receive actions:read")
    require("actions/download-artifact@" in decision, "NODE-71 artifact download must remain inside the actions:read job")


def validate_deploy() -> None:
    source = text(DEPLOY)
    header = top(source)
    require("permissions:\n  contents: read\n  actions: read\n" in header, "production deploy top-level permissions must be read-only")
    require("id-token: write" not in header, "production deploy must not grant OIDC at workflow scope")
    for forbidden in ("contents: write", "actions: write", "packages: write", "attestations: write"):
        require(forbidden not in header, f"production deploy top-level permission too broad: {forbidden}")
    release = job_block(source, "release-gate", "production")
    production = job_block(source, "production", None)
    require("id-token: write" not in release and "aws-actions/configure-aws-credentials@" not in release, "release-gate must not receive production AWS identity")
    require("needs: [release-gate]" in production and "environment: production" in production, "production mutation must depend on protected release gate")
    require("permissions:\n      contents: read\n      id-token: write\n" in production, "OIDC must be scoped only to protected production job")
    require("actions: read" not in production and "aws-actions/configure-aws-credentials@" in production, "production OIDC boundary drift")


def validate_final() -> None:
    source = text(FINAL)
    require_top_read_only(source, "Final Product Acceptance")
    header = top(source)
    require("pull-requests: read" not in header, "Final Acceptance must not grant PR review access at workflow scope")
    source_contract = job_block(source, "source-contract", "canonical-lock-gate")
    lock_gate = job_block(source, "canonical-lock-gate", "final-decision")
    final_decision = job_block(source, "final-decision", "contract-gate")
    for label, block in (("source-contract", source_contract), ("canonical-lock-gate", lock_gate)):
        require("pull-requests: read" not in block, f"NODE-73 Final Acceptance {label} may not receive PR read permission")
    require("permissions:\n      contents: read\n      pull-requests: read\n" in final_decision, "only final-decision may receive pull-requests:read")
    for forbidden in ("contents: write", "pull-requests: write", "actions: write", "packages: write", "attestations: write", "id-token: write"):
        require(forbidden not in final_decision, f"Final Acceptance final-decision has unnecessary write capability: {forbidden}")
    require('RELEASE_APPROVAL_TOKEN: ${{ secrets.GITHUB_TOKEN }}' in final_decision, "Final Acceptance must use ephemeral GITHUB_TOKEN for live PR review verification")
    require("RELEASE_APPROVAL_TOKEN:" not in header + source_contract + lock_gate, "approval token must not escape final-decision")


def main() -> int:
    validate_assemble()
    validate_governance_apply()
    validate_build()
    validate_lock()
    validate_staging()
    validate_deploy()
    validate_final()
    for path, label in ((RUNTIME, "Runtime Image Closure"), (PROD_IAC, "Production IaC Contract")):
        require_top_read_only(text(path), label)
    print("NODE-73 release workflow least-privilege contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PermissionContractError, OSError) as exc:
        raise SystemExit(f"release workflow permission contract failed: {exc}") from exc

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSEMBLE = ROOT / ".github" / "workflows" / "assemble-final-acceptance.yml"
BUILD = ROOT / ".github" / "workflows" / "build-runtime-image-set.yml"
LOCK = ROOT / ".github" / "workflows" / "regenerate-uv-lock.yml"
RUNTIME = ROOT / ".github" / "workflows" / "runtime-image-closure-contract.yml"
STAGING = ROOT / ".github" / "workflows" / "staging-acceptance-gate.yml"
PROD_IAC = ROOT / ".github" / "workflows" / "production-iac-contract.yml"
DEPLOY = ROOT / ".github" / "workflows" / "deploy-production.yml"
FINAL = ROOT / ".github" / "workflows" / "final-acceptance-gate.yml"


class PermissionContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PermissionContractError(message)


def text(path: Path) -> str:
    if not path.is_file():
        raise PermissionContractError(f"missing release workflow: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def job_block(source: str, job: str, next_job: str | None) -> str:
    marker = f"  {job}:\n"
    start = source.find(marker)
    if start < 0:
        raise PermissionContractError(f"missing workflow job: {job}")
    if next_job is None:
        return source[start:]
    end = source.find(f"  {next_job}:\n", start + len(marker))
    if end < 0:
        raise PermissionContractError(f"missing workflow job terminator: {next_job}")
    return source[start:end]


def top(source: str) -> str:
    end = source.find("jobs:\n")
    if end < 0:
        raise PermissionContractError("workflow has no jobs section")
    return source[:end]


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
    require(
        "permissions:\n      contents: write\n" in assemble,
        "only Final Acceptance assembler job may receive contents:write",
    )
    for forbidden in ("actions: write", "packages: write", "attestations: write", "id-token: write", "pull-requests: write"):
        require(forbidden not in assemble, f"Final Acceptance assembler has unrelated write capability: {forbidden}")
    require("github.ref == 'refs/heads/release-closure-p0'" in assemble, "Final Acceptance assembler must be release-closure-p0-only")
    require('ref: ${{ github.sha }}' in assemble and "fetch-depth: 0" in assemble, "Final Acceptance assembler must checkout exact dispatch SHA with full history")
    require('git push origin "HEAD:${GITHUB_REF_NAME}"' in assemble, "Final Acceptance assembler must push only the current release branch")
    require("git push --force" not in assemble.casefold(), "Final Acceptance assembler must never force-push")
    require('test "$remote_sha" = "$GITHUB_SHA"' in assemble, "Final Acceptance assembler must fail closed if release branch moves")
    require("final-acceptance-assembler-v2.py" in assemble, "Final Acceptance assembler must use V2 package producer")
    require("final-acceptance-assembler.py" not in assemble, "Final Acceptance assembler must not use V1 package producer")


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
    require("docker/login-action@" not in read_gate, "read-only source-gate must not log in to registry")
    require("docker/build-push-action@" not in read_gate, "read-only source-gate must not push images")
    require("actions/attest@" not in read_gate, "read-only source-gate must not attest images")


def validate_lock() -> None:
    source = text(LOCK)
    header = top(source)
    require("permissions:\n  contents: write\n" in header, "uv-lock workflow needs exactly contents:write")
    for forbidden in ("actions: write", "packages: write", "attestations: write", "id-token: write"):
        require(forbidden not in header, f"uv-lock workflow has unrelated write capability: {forbidden}")
    require("git add -- uv.lock" in source, "uv-lock workflow must retain narrow file mutation")
    require("git push --force" not in source.casefold(), "uv-lock workflow must not force-push")


def validate_staging() -> None:
    source = text(STAGING)
    require_top_read_only(source, "NODE-71 staging acceptance")
    source_contract = job_block(source, "source-contract", "canonical-lock-gate")
    lock_gate = job_block(source, "canonical-lock-gate", "remote-read-only-preflight")
    preflight = job_block(source, "remote-read-only-preflight", "acceptance-decision")
    decision = job_block(source, "acceptance-decision", "contract-gate")
    for label, block in (("source-contract", source_contract), ("canonical-lock-gate", lock_gate), ("remote-read-only-preflight", preflight)):
        require("actions: read" not in block, f"NODE-71 {label} must not receive cross-run artifact read permission")
    require(
        "permissions:\n      contents: read\n      actions: read\n" in decision,
        "only NODE-71 acceptance-decision may receive actions:read",
    )
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
    require("id-token: write" not in release, "release-gate must not be able to mint OIDC tokens")
    require("aws-actions/configure-aws-credentials@" not in release, "release-gate must not assume the production AWS role")
    require("needs: [release-gate]" in production, "production mutation job must depend on release-gate")
    require("environment: production" in production, "OIDC-capable production job must remain protected by the production environment")
    require(
        "permissions:\n      contents: read\n      id-token: write\n" in production,
        "OIDC must be scoped only to the protected production job",
    )
    require("actions: read" not in production, "production mutation job does not need cross-run Actions read permission")
    require("aws-actions/configure-aws-credentials@" in production, "production OIDC job must contain the exact AWS assume-role boundary")


def validate_final() -> None:
    source = text(FINAL)
    require_top_read_only(source, "Final Product Acceptance")
    header = top(source)
    require("pull-requests: read" not in header, "Final Acceptance must not grant PR review access at workflow scope")
    source_contract = job_block(source, "source-contract", "canonical-lock-gate")
    lock_gate = job_block(source, "canonical-lock-gate", "final-decision")
    final_decision = job_block(source, "final-decision", "contract-gate")
    for label, block in (("source-contract", source_contract), ("canonical-lock-gate", lock_gate)):
        require("pull-requests: read" not in block, f"Final Acceptance {label} must not receive PR review access")
    require(
        "permissions:\n      contents: read\n      pull-requests: read\n" in final_decision,
        "only Final Acceptance final-decision may receive pull-requests:read",
    )
    for forbidden in ("contents: write", "pull-requests: write", "actions: write", "packages: write", "attestations: write", "id-token: write"):
        require(forbidden not in final_decision, f"Final Acceptance final-decision has unnecessary write capability: {forbidden}")
    require(
        'RELEASE_APPROVAL_TOKEN: ${{ secrets.GITHUB_TOKEN }}' in final_decision,
        "Final Acceptance must use the ephemeral GitHub token for live PR-review verification",
    )
    require(
        "RELEASE_APPROVAL_TOKEN:" not in header + source_contract + lock_gate,
        "Final Acceptance approval token must not be exposed outside final-decision",
    )


def main() -> int:
    validate_assemble()
    validate_build()
    validate_lock()
    validate_staging()
    validate_deploy()
    validate_final()
    for path, label in (
        (RUNTIME, "Runtime Image Closure"),
        (PROD_IAC, "Production IaC Contract"),
    ):
        require_top_read_only(text(path), label)
    print("NODE-73 release workflow least-privilege contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PermissionContractError, OSError) as exc:
        raise SystemExit(f"release workflow permission contract failed: {exc}") from exc

#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "production" / "runtime-images" / "manifest-v1.json"
WORKFLOW = ROOT / ".github" / "workflows" / "build-runtime-image-set.yml"
ATTESTATION_VERIFIER = ROOT / "scripts" / "verify_runtime_image_attestations.py"
EXPECTED = {
    "api": "apps/api/Dockerfile",
    "agent-runtime": "apps/agent-runtime/Dockerfile",
    "model-gateway": "services/model-gateway/Dockerfile",
    "tool-gateway": "services/tool-gateway/Dockerfile",
    "worker-media": "apps/worker-media/Dockerfile",
    "sandbox-runtime": "services/sandbox-runtime/Dockerfile",
}
PINNED_ACTIONS = {
    "checkout": "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6.1.0",
    "setup-python": "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0",
    "setup-uv": "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0",
    "login": "docker/login-action@dbcb813823bdd20940b903addbd779551569679f # v4.6.0",
    "buildx": "docker/setup-buildx-action@bb05f3f5519dd87d3ba754cc423b652a5edd6d2c # v4.2.0",
    "build-push": "docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a # v7.3.0",
    "attest": "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4.2.2",
    "upload": "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1",
}


class PipelineContractError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PipelineContractError(message)


def _load_manifest() -> dict[str, object]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), "runtime image manifest must be an object")
    _require(payload.get("schema_version") == 1, "runtime image manifest schema drift")
    runtimes = payload.get("runtimes")
    _require(isinstance(runtimes, dict), "runtime image manifest runtimes missing")
    _require(set(runtimes) == set(EXPECTED), "runtime image manifest must contain exactly six runtimes")
    for service, dockerfile in EXPECTED.items():
        item = runtimes.get(service)
        _require(isinstance(item, dict), f"runtime image manifest entry missing: {service}")
        _require(item.get("dockerfile") == dockerfile, f"{service} Dockerfile mapping drift")
        _require((ROOT / dockerfile).is_file(), f"{service} Dockerfile missing")
        sources = item.get("source_paths")
        _require(isinstance(sources, list) and len(sources) > 0, f"{service} provenance sources missing")
    return payload


def _block(text: str, start_marker: str, next_marker: str | None) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise PipelineContractError(f"workflow missing block: {start_marker}")
    if next_marker is None:
        return text[start:]
    end = text.find(next_marker, start + len(start_marker))
    if end < 0:
        raise PipelineContractError(f"workflow block {start_marker} missing terminator {next_marker}")
    return text[start:end]


def validate_attestation_verifier() -> None:
    text = ATTESTATION_VERIFIER.read_text(encoding="utf-8")
    for marker in (
        'RELEASE_SOURCE_REF = "refs/heads/release-closure-p0"',
        'SIGNER_WORKFLOW_PATH = ".github/workflows/build-runtime-image-set.yml"',
        'env.get("GITHUB_SHA", "").lower()',
        'env.get("GITHUB_REF", "")',
        'env.get("GITHUB_WORKFLOW_REF", "")',
        '"--signer-workflow"',
        '"--source-digest"',
        '"--source-ref"',
        '"--deny-self-hosted-runners"',
        '"github_attestation_policy"',
        '"signer_workflow": policy.signer_workflow',
        '"source_digest": policy.source_digest',
        '"source_ref": policy.source_ref',
        '"workflow_ref": policy.workflow_ref',
        '"deny_self_hosted_runners": policy.deny_self_hosted_runners',
        "bad_identity_envs = [",
    ):
        _require(marker in text, f"runtime attestation verifier missing signer/source identity marker: {marker}")

    command_start = text.find('"gh",\n            "attestation",\n            "verify"')
    signer_pos = text.find('"--signer-workflow"', command_start)
    digest_pos = text.find('"--source-digest"', command_start)
    ref_pos = text.find('"--source-ref"', command_start)
    hosted_pos = text.find('"--deny-self-hosted-runners"', command_start)
    _require(
        command_start >= 0
        and command_start < signer_pos < digest_pos < ref_pos < hosted_pos,
        "GitHub attestation verification must enforce signer workflow, source digest/ref, and hosted runner identity",
    )
    _require(
        "policy = resolve_github_attestation_policy(args.repository, os.environ)" in text,
        "live verifier must derive signer/source identity from immutable GitHub Actions environment",
    )


def validate_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for marker in (
        "workflow_dispatch:",
        "  source-gate:\n",
        "  build-and-freeze:\n",
        "needs: [source-gate]",
        "packages: write",
        "attestations: write",
        "id-token: write",
        "github.ref_name == 'release-closure-p0'",
        "ref: ${{ github.sha }}",
        'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
        "python3 scripts/validate_uv_workspace_lock.py",
        "uv lock --check",
        "uv sync --all-packages --frozen",
        "python3 scripts/validate_release_action_pins.py",
        "python3 scripts/validate_uv_lock_regeneration_contract.py",
        "python3 scripts/validate_runtime_image_closure.py",
        "python3 scripts/runtime_image_set.py validate-manifest",
        "python3 scripts/verify_runtime_image_attestations.py --self-test",
        "python3 scripts/validate_runtime_image_build_pipeline.py",
        PINNED_ACTIONS["checkout"],
        PINNED_ACTIONS["setup-python"],
        PINNED_ACTIONS["setup-uv"],
        PINNED_ACTIONS["login"],
        PINNED_ACTIONS["buildx"],
        PINNED_ACTIONS["build-push"],
        PINNED_ACTIONS["attest"],
        "python3 scripts/verify_runtime_image_attestations.py",
        'GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}',
        "attestation-verification.json",
        "python3 scripts/runtime_image_set.py assemble",
        PINNED_ACTIONS["upload"],
        "runtime-image-set-${{ github.sha }}",
    ):
        _require(marker in text, f"runtime image build workflow missing: {marker}")

    top = text[: text.find("jobs:\n")]
    _require(
        "permissions:\n  contents: read\n" in top,
        "runtime image workflow top-level token must be read-only",
    )
    for permission in ("packages: write", "attestations: write", "id-token: write", "contents: write"):
        _require(permission not in top, f"runtime image workflow top-level permission is too broad: {permission}")

    source = _block(text, "  source-gate:\n", "  build-and-freeze:\n")
    build = _block(text, "  build-and-freeze:\n", None)

    _require("permissions:\n      contents: read\n" in source, "source-gate must explicitly remain contents-read-only")
    for permission in ("packages: write", "attestations: write", "id-token: write", "contents: write"):
        _require(permission not in source, f"source-gate must not receive write capability: {permission}")
    for marker in (
        "python3 scripts/validate_release_action_pins.py",
        "python3 scripts/validate_uv_lock_regeneration_contract.py",
        "python3 scripts/validate_runtime_image_closure.py",
        "python3 scripts/verify_runtime_image_attestations.py --self-test",
        "python3 scripts/validate_runtime_image_build_pipeline.py",
        "python3 scripts/validate_uv_workspace_lock.py",
        "uv lock --check",
        "uv sync --all-packages --frozen",
    ):
        _require(marker in source, f"read-only source-gate missing prerequisite: {marker}")
    _require(PINNED_ACTIONS["login"] not in source, "source-gate must not authenticate to the package registry")
    _require(PINNED_ACTIONS["build-push"] not in source, "source-gate must not build/push release images")
    _require(PINNED_ACTIONS["attest"] not in source, "source-gate must not create attestations")

    _require("needs: [source-gate]" in build, "write-capable image build must depend on source-gate")
    for permission in ("contents: read", "packages: write", "attestations: write", "id-token: write"):
        _require(permission in build, f"build-and-freeze missing scoped permission: {permission}")
    _require("ref: ${{ github.sha }}" in build, "write-capable build must checkout exact dispatch SHA")
    _require(
        'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in build,
        "write-capable build must re-bind checkout HEAD to dispatch SHA",
    )

    source_pos = text.find("  source-gate:\n")
    build_pos = text.find("  build-and-freeze:\n")
    registry_login_pos = text.find(PINNED_ACTIONS["login"])
    _require(
        0 <= source_pos < build_pos < registry_login_pos,
        "read-only source-gate definition must precede the privileged image build path",
    )
    _require(text.count("ref: ${{ github.sha }}") >= 2, "both source-gate and build job must checkout exact dispatch SHA")
    _require("latest" not in text.casefold(), "runtime image build workflow must not publish a latest tag")
    _require(text.count("provenance: mode=max") == 6, "all six images require max provenance")
    _require(text.count("sbom: true") == 6, "all six images require SBOM attestation")
    _require(text.count("push-to-registry: true") == 6, "all six images require GitHub registry attestation")
    _require(text.count(PINNED_ACTIONS["build-push"]) == 6, "all six builds must use the approved immutable build-push action")
    _require(text.count(PINNED_ACTIONS["attest"]) == 6, "all six attestations must use the approved immutable attest action")
    _require(
        text.count("python3 scripts/runtime_image_set.py fragment") == 6,
        "all six image digests must produce freeze fragments",
    )
    _require(text.count("@${{ steps.build_") >= 12, "attestation verification and frozen refs must use exact build-step digests")

    verification = _block(
        build,
        "- name: Verify all six immutable runtime image attestations",
        "- name: Freeze exact six-image set for NODE-71",
    )
    _require('GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}' in verification, "GitHub attestation verification must receive the workflow token")
    _require("python3 scripts/verify_runtime_image_attestations.py" in verification, "live attestation verifier is missing")
    _require('--repository "$GITHUB_REPOSITORY"' in verification, "attestation verification must bind repository identity")
    for service in EXPECTED:
        _require(f'--image "{service}=' in verification, f"attestation verification is missing runtime: {service}")
    _require(
        '--out "${root}/attestation-verification.json"' in verification,
        "attestation verification must persist one report beside the frozen image set",
    )

    last_attest_pos = build.rfind(PINNED_ACTIONS["attest"])
    verify_pos = build.find("- name: Verify all six immutable runtime image attestations")
    freeze_pos = build.find("- name: Freeze exact six-image set for NODE-71")
    upload_pos = build.find("- name: Upload frozen six-runtime RC image set")
    _require(
        min(last_attest_pos, verify_pos, freeze_pos, upload_pos) >= 0
        and last_attest_pos < verify_pos < freeze_pos < upload_pos,
        "all six image attestations must be live-verified before NODE-71 freeze and upload",
    )

    freeze_block = _block(text, "- name: Freeze exact six-image set for NODE-71", "- name: Upload frozen six-runtime RC image set")
    _require('test -f "${root}/attestation-verification.json"' in freeze_block, "freeze must require the attestation verification report")
    _require('.get("status")' in freeze_block and '= "PASS"' in freeze_block, "freeze must fail closed unless attestation verification status is PASS")
    for service in EXPECTED:
        _require(f"--service {service}" in freeze_block, f"{service} freeze fragment missing")
        _require(f"-{service}@${{{{ steps.build_" in freeze_block, f"{service} immutable digest freeze missing")
    _require("--git-sha \"$GITHUB_SHA\"" in freeze_block, "frozen set must bind exact Git SHA")
    _require("#attestation=sbom" in freeze_block, "frozen set must retain SBOM reference")
    _require("--provenance-ref" in freeze_block, "frozen set must retain provenance reference")


def main() -> int:
    _load_manifest()
    validate_attestation_verifier()
    validate_workflow()
    print("Six-runtime RC image signer/source attestation/freeze pipeline contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PipelineContractError as exc:
        raise SystemExit(f"runtime image build pipeline contract failed: {exc}") from exc

#!/usr/bin/env python3
from __future__ import annotations

import json
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "production" / "runtime-images" / "manifest-v1.json"
WORKFLOW = ROOT / ".github" / "workflows" / "build-runtime-image-set.yml"
CLOSURE_WORKFLOW = ROOT / ".github" / "workflows" / "runtime-image-closure-contract.yml"
ATTESTATION_VERIFIER = ROOT / "scripts" / "verify_runtime_image_attestations.py"
DOCKERIGNORE = ROOT / ".dockerignore"
EXPECTED = {
    "api": "apps/api/Dockerfile",
    "agent-runtime": "apps/agent-runtime/Dockerfile",
    "model-gateway": "services/model-gateway/Dockerfile",
    "tool-gateway": "services/tool-gateway/Dockerfile",
    "worker-media": "apps/worker-media/Dockerfile",
    "sandbox-runtime": "services/sandbox-runtime/Dockerfile",
}
BUILD_BINDINGS = {
    "api": ("API", "api", "build_api", "attest_api", "API_PROVENANCE"),
    "agent-runtime": (
        "Agent Runtime",
        "agent-runtime",
        "build_agent_runtime",
        "attest_agent_runtime",
        "AGENT_PROVENANCE",
    ),
    "model-gateway": (
        "Model Gateway",
        "model-gateway",
        "build_model_gateway",
        "attest_model_gateway",
        "MODEL_PROVENANCE",
    ),
    "tool-gateway": (
        "Tool Gateway",
        "tool-gateway",
        "build_tool_gateway",
        "attest_tool_gateway",
        "TOOL_PROVENANCE",
    ),
    "worker-media": (
        "Worker Media",
        "worker-media",
        "build_worker_media",
        "attest_worker_media",
        "WORKER_PROVENANCE",
    ),
    "sandbox-runtime": (
        "Sandbox Runtime",
        "sandbox-runtime",
        "build_sandbox_runtime",
        "attest_sandbox_runtime",
        "SANDBOX_PROVENANCE",
    ),
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
UV_BASE_TAG = "ghcr.io/astral-sh/uv:0.11.28"
PYTHON_BASE_TAG = "python:3.12-slim"
DOCKERFILE_BASE_MARKERS = (
    f"ARG UV_BASE_IMAGE={UV_BASE_TAG}",
    f"ARG PYTHON_BASE_IMAGE={PYTHON_BASE_TAG}",
    "FROM ${UV_BASE_IMAGE} AS uv",
    "FROM ${PYTHON_BASE_IMAGE}",
)


class PipelineContractError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PipelineContractError(message)


def _dockerignore_candidates(source: str) -> tuple[str, ...]:
    path = PurePosixPath(source.strip("/"))
    parts = path.parts
    return tuple("/".join(parts[:index]) for index in range(1, len(parts) + 1))


def _positive_ignore_rule_matches(rule: str, source: str) -> bool:
    pattern = rule.strip().lstrip("/")
    if not pattern or pattern.startswith("!"):
        return False
    if pattern.endswith("/"):
        pattern = pattern.rstrip("/") + "/**"
    for candidate in _dockerignore_candidates(source):
        if fnmatchcase(candidate, pattern):
            return True
        if "/" not in pattern and fnmatchcase(PurePosixPath(candidate).name, pattern):
            return True
    return False


def _validate_dockerignore(payload: dict[str, object]) -> None:
    _require(DOCKERIGNORE.is_file(), ".dockerignore is missing from the root build context")
    rules = [
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    runtimes = payload.get("runtimes")
    _require(isinstance(runtimes, dict), "runtime image manifest runtimes missing")
    for service, item in runtimes.items():
        _require(isinstance(item, dict), f"runtime image manifest entry missing: {service}")
        sources = item.get("source_paths")
        _require(isinstance(sources, list), f"{service} provenance sources missing")
        for raw_source in sources:
            source = str(raw_source)
            for rule in rules:
                if rule.startswith("!"):
                    continue
                _require(
                    not _positive_ignore_rule_matches(rule, source),
                    f".dockerignore rule {rule!r} can remove declared {service} provenance source {source!r}",
                )


def _validate_dockerfile_base_image_contract() -> None:
    for service, relative in EXPECTED.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for marker in DOCKERFILE_BASE_MARKERS:
            _require(marker in text, f"{service} Dockerfile missing release base-image parameter marker: {marker}")
        _require(
            f"FROM {UV_BASE_TAG}" not in text and f"FROM {PYTHON_BASE_TAG}" not in text,
            f"{service} Dockerfile must consume release-resolved base-image args rather than direct mutable FROM tags",
        )
        _require("COPY . /workspace" in text, f"{service} Dockerfile must copy the exact root Git context into /workspace")
        _require(
            "uv sync --all-packages --frozen --no-dev" in text,
            f"{service} Dockerfile must consume the canonical frozen workspace dependency graph",
        )


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
    _validate_dockerignore(payload)
    _validate_dockerfile_base_image_contract()
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
        'BUILDKIT_BUILD_TYPE = "https://mobyproject.org/buildkit@v1"',
        'BUILDKIT_PLATFORM = "linux/amd64"',
        'EXPECTED_DOCKERFILES = {',
        'EXPECTED_BASE_IMAGE_PREFIXES = {',
        '"UV_BASE_IMAGE": "ghcr.io/astral-sh/uv@sha256:"',
        '"PYTHON_BASE_IMAGE": "python@sha256:"',
        'env.get("GITHUB_SHA", "").lower()',
        'env.get("GITHUB_REF", "")',
        'env.get("GITHUB_WORKFLOW_REF", "")',
        '"--signer-workflow"',
        '"--source-digest"',
        '"--source-ref"',
        '"--deny-self-hosted-runners"',
        'config_source = invocation.get("configSource")',
        'config_source.get("entryPoint") == dockerfile',
        'source_digests.get("sha1") == source_digest',
        'environment.get("platform") == BUILDKIT_PLATFORM',
        '_validate_base_image_build_args(invocation)',
        'f"build-arg:{arg_name}"',
        'bool(IMAGE_REF.fullmatch(value))',
        '"base_images": base_images',
        '"material_sha256_count": len(material_digests)',
        '"source_uri": source_uri',
        '"github_attestation_policy"',
        "bad_identity_envs = [",
        "bad_provenance = [",
    ):
        _require(marker in text, f"runtime attestation verifier missing immutable signer/source/base marker: {marker}")

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
    _require(
        "repository=policy.repository" in text
        and "source_digest=policy.source_digest" in text
        and "dockerfile=EXPECTED_DOCKERFILES[target.service]" in text,
        "live BuildKit provenance validation must bind repository, RC SHA, and runtime Dockerfile",
    )


def _validate_exact_runtime_build_blocks(text: str) -> None:
    ordered = list(EXPECTED)
    for index, service in enumerate(ordered):
        display, image_suffix, build_id, attest_id, provenance_env = BUILD_BINDINGS[service]
        dockerfile = EXPECTED[service]
        build_marker = f"- name: Build and push {display}"
        attest_marker = f"- name: Attest {display} image"
        if index + 1 < len(ordered):
            next_display = BUILD_BINDINGS[ordered[index + 1]][0]
            next_marker = f"- name: Build and push {next_display}"
        else:
            next_marker = "- name: Verify all six immutable runtime image attestations"

        build_block = _block(text, build_marker, attest_marker)
        attest_block = _block(text, attest_marker, next_marker)
        build_markers = (
            f"id: {build_id}",
            PINNED_ACTIONS["build-push"],
            "context: https://github.com/${{ github.repository }}.git#${{ github.sha }}",
            f"file: {dockerfile}",
            "platforms: linux/amd64",
            "push: true",
            "tags: ${{ env.IMAGE_BASE }}-" + image_suffix + ":rc-${{ github.sha }}",
            "build-args: |",
            "UV_BASE_IMAGE=${{ env.UV_BASE_IMAGE }}",
            "PYTHON_BASE_IMAGE=${{ env.PYTHON_BASE_IMAGE }}",
            "provenance: mode=max,version=v0.2",
            "sbom: true",
            "secrets: |",
            "GIT_AUTH_TOKEN=${{ secrets.GITHUB_TOKEN }}",
        )
        for marker in build_markers:
            _require(marker in build_block, f"{service} build block missing exact immutable input binding: {marker}")

        attest_markers = (
            f"id: {attest_id}",
            PINNED_ACTIONS["attest"],
            "subject-name: ${{ env.IMAGE_BASE }}-" + image_suffix,
            "subject-digest: ${{ steps." + build_id + ".outputs.digest }}",
            "push-to-registry: true",
        )
        for marker in attest_markers:
            _require(marker in attest_block, f"{service} attestation block missing exact build binding: {marker}")

        _require(
            provenance_env
            + ": ${{ steps."
            + attest_id
            + ".outputs['attestation-url'] }}" in text,
            f"{service} frozen provenance reference must come from its own attestation step",
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
        f"UV_BASE_TAG: {UV_BASE_TAG}",
        f"PYTHON_BASE_TAG: {PYTHON_BASE_TAG}",
        "- name: Resolve immutable base image digests once",
        'docker buildx imagetools inspect "$image" --format \'{{json .Manifest}}\'',
        're.fullmatch(r"sha256:[0-9a-f]{64}", value)',
        'uv_image="ghcr.io/astral-sh/uv@${uv_digest}"',
        'python_image="python@${python_digest}"',
        'echo "UV_BASE_IMAGE=${uv_image}" >> "$GITHUB_ENV"',
        'echo "PYTHON_BASE_IMAGE=${python_image}" >> "$GITHUB_ENV"',
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
    buildx_pos = text.find(PINNED_ACTIONS["buildx"])
    base_resolve_pos = text.find("- name: Resolve immutable base image digests once")
    first_build_pos = text.find("- name: Build and push API")
    _require(
        0 <= source_pos < build_pos < registry_login_pos < buildx_pos < base_resolve_pos < first_build_pos,
        "release must pass read-only source gate, authenticate, initialize Buildx, freeze base digests, then build",
    )
    _require(text.count("ref: ${{ github.sha }}") >= 2, "both source-gate and build job must checkout exact dispatch SHA")
    _require("latest" not in text.casefold(), "runtime image build workflow must not publish a latest tag")
    immutable_context = "context: https://github.com/${{ github.repository }}.git#${{ github.sha }}"
    _require(text.count(immutable_context) == 6, "all six images must build from the immutable RC Git context")
    _require("context: ." not in build, "release runtime images must not use mutable local path context")
    _require("{{defaultContext}}" not in build, "release runtime images must not build from a mutable branch/ref default context")
    _require(text.count("GIT_AUTH_TOKEN=${{ secrets.GITHUB_TOKEN }}") == 6, "all six immutable private Git contexts require scoped Git auth")
    _require(text.count("build-args: |") == 6, "all six release images must receive immutable base-image build args")
    _require(text.count("UV_BASE_IMAGE=${{ env.UV_BASE_IMAGE }}") == 6, "all six release images must use the one resolved uv digest")
    _require(text.count("PYTHON_BASE_IMAGE=${{ env.PYTHON_BASE_IMAGE }}") == 6, "all six release images must use the one resolved Python digest")
    _require(text.count("provenance: mode=max,version=v0.2") == 6, "all six images require pinned max SLSA v0.2 provenance")
    _require(text.count("sbom: true") == 6, "all six images require SBOM attestation")
    _require(text.count("push-to-registry: true") == 6, "all six images require GitHub registry attestation")
    _require(text.count(PINNED_ACTIONS["build-push"]) == 6, "all six builds must use the approved immutable build-push action")
    _require(text.count(PINNED_ACTIONS["attest"]) == 6, "all six attestations must use the approved immutable attest action")
    _require(
        text.count("python3 scripts/runtime_image_set.py fragment") == 6,
        "all six image digests must produce freeze fragments",
    )
    _validate_exact_runtime_build_blocks(build)

    verification = _block(
        build,
        "- name: Verify all six immutable runtime image attestations",
        "- name: Freeze exact six-image set for NODE-71",
    )
    _require('GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}' in verification, "GitHub attestation verification must receive the workflow token")
    _require("python3 scripts/verify_runtime_image_attestations.py" in verification, "live attestation verifier is missing")
    _require('--repository "$GITHUB_REPOSITORY"' in verification, "attestation verification must bind repository identity")
    for service in EXPECTED:
        _, image_suffix, build_id, _, _ = BUILD_BINDINGS[service]
        exact_image = (
            '--image "'
            + service
            + '=${IMAGE_BASE}-'
            + image_suffix
            + '@${{ steps.'
            + build_id
            + '.outputs.digest }}"'
        )
        _require(exact_image in verification, f"attestation verification is not bound to {service} build digest")
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
        _, image_suffix, build_id, _, provenance_env = BUILD_BINDINGS[service]
        _require(f"--service {service}" in freeze_block, f"{service} freeze fragment missing")
        exact_image = (
            '--image "${IMAGE_BASE}-'
            + image_suffix
            + '@${{ steps.'
            + build_id
            + '.outputs.digest }}"'
        )
        _require(exact_image in freeze_block, f"{service} frozen image is not bound to its own build digest")
        exact_sbom = (
            '--sbom-ref "oci://${IMAGE_BASE}-'
            + image_suffix
            + '@${{ steps.'
            + build_id
            + '.outputs.digest }}#attestation=sbom"'
        )
        _require(exact_sbom in freeze_block, f"{service} frozen SBOM is not bound to its own build digest")
        _require(
            '--provenance-ref "$' + provenance_env + '"' in freeze_block,
            f"{service} frozen provenance is not bound to its own attestation output",
        )
    _require("--git-sha \"$GITHUB_SHA\"" in freeze_block, "frozen set must bind exact Git SHA")

    closure = CLOSURE_WORKFLOW.read_text(encoding="utf-8")
    _require(
        '- ".dockerignore"' in closure,
        "Runtime Image Closure pull_request paths must include .dockerignore build-context changes",
    )
    for dockerfile in EXPECTED.values():
        _require(f'- "{dockerfile}"' in closure, f"Runtime Image Closure must trigger on {dockerfile}")
    _require(
        'scripts/validate_runtime_image_build_pipeline.py' in closure,
        "Runtime Image Closure must continue executing the build-pipeline validator",
    )


def main() -> int:
    _load_manifest()
    validate_attestation_verifier()
    validate_workflow()
    print("Six-runtime RC immutable Git/base-image/signer/recipe/digest attestation/freeze pipeline contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PipelineContractError as exc:
        raise SystemExit(f"runtime image build pipeline contract failed: {exc}") from exc

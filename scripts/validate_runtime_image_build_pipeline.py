#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "production" / "runtime-images" / "manifest-v1.json"
WORKFLOW = ROOT / ".github" / "workflows" / "build-runtime-image-set.yml"
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


def validate_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for marker in (
        "workflow_dispatch:",
        "packages: write",
        "attestations: write",
        "id-token: write",
        "github.ref_name == 'release-closure-p0'",
        "python3 scripts/validate_uv_workspace_lock.py",
        "uv lock --check",
        "uv sync --all-packages --frozen",
        "python3 scripts/validate_release_action_pins.py",
        "python3 scripts/validate_runtime_image_closure.py",
        "python3 scripts/runtime_image_set.py validate-manifest",
        PINNED_ACTIONS["checkout"],
        PINNED_ACTIONS["setup-python"],
        PINNED_ACTIONS["setup-uv"],
        PINNED_ACTIONS["login"],
        PINNED_ACTIONS["buildx"],
        PINNED_ACTIONS["build-push"],
        PINNED_ACTIONS["attest"],
        "docker buildx imagetools inspect",
        "python3 scripts/runtime_image_set.py assemble",
        PINNED_ACTIONS["upload"],
        "runtime-image-set-${{ github.sha }}",
    ):
        _require(marker in text, f"runtime image build workflow missing: {marker}")

    pin_pos = text.find("python3 scripts/validate_release_action_pins.py")
    registry_login_pos = text.find(PINNED_ACTIONS["login"])
    _require(
        pin_pos >= 0 and registry_login_pos >= 0 and pin_pos < registry_login_pos,
        "release action pin self-check must run before registry login/package writes",
    )
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
    _require(text.count("@${{ steps.build_") >= 6, "frozen image refs must use build-step digests")

    ordered = list(EXPECTED.items())
    for index, (service, dockerfile) in enumerate(ordered):
        build_marker = f"file: {dockerfile}"
        next_marker = f"file: {ordered[index + 1][1]}" if index + 1 < len(ordered) else None
        block = _block(text, build_marker, next_marker)
        _require("push: true" in block, f"{service} image must be pushed")
        _require("provenance: mode=max" in block, f"{service} image max provenance missing")
        _require("sbom: true" in block, f"{service} image SBOM missing")
        _require(f"-{service}:rc-${{{{ github.sha }}}}" in block, f"{service} RC tag binding missing")

    freeze_block = _block(text, "- name: Freeze exact six-image set for NODE-71", "- name: Upload frozen six-runtime RC image set")
    for service in EXPECTED:
        _require(f"--service {service}" in freeze_block, f"{service} freeze fragment missing")
        _require(f"-{service}@${{{{ steps.build_" in freeze_block, f"{service} immutable digest freeze missing")
    _require("--git-sha \"$GITHUB_SHA\"" in freeze_block, "frozen set must bind exact Git SHA")
    _require("#attestation=sbom" in freeze_block, "frozen set must retain SBOM reference")
    _require("--provenance-ref" in freeze_block, "frozen set must retain provenance reference")


def main() -> int:
    _load_manifest()
    validate_workflow()
    print("Six-runtime RC image build/freeze pipeline contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PipelineContractError as exc:
        raise SystemExit(f"runtime image build pipeline contract failed: {exc}") from exc

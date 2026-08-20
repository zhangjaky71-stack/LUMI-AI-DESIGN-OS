#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
STAGING_GATE = ROOT / "scripts" / "staging-acceptance-gate.py"
RUNTIME_MANIFEST = ROOT / "production" / "runtime-images" / "manifest-v1.json"
REQUIRED_RUNTIMES = {
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
}


class BindingError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BindingError(f"unable to read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BindingError(f"{path} must contain a JSON object")
    return payload


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_staging_acceptance_gate", STAGING_GATE)
    if spec is None or spec.loader is None:
        raise BindingError("unable to import staging acceptance gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_run_id(value: str) -> str:
    if not value.isdecimal() or int(value) <= 0:
        raise BindingError("runtime image build run id must be a positive decimal GitHub Actions run id")
    return value


def _run_id_from_url(build_run_url: str) -> str:
    parsed = urlsplit(build_run_url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.query or parsed.fragment:
        raise BindingError("runtime image build_run_url must be a canonical github.com HTTPS run URL")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 5 or parts[2:4] != ["actions", "runs"]:
        raise BindingError("runtime image build_run_url must use /<owner>/<repo>/actions/runs/<id>")
    return _validate_run_id(parts[4])


def expected_image_set_ref(*, build_run_url: str, git_sha: str) -> str:
    _run_id_from_url(build_run_url)
    if len(git_sha) != 40 or any(char not in "0123456789abcdef" for char in git_sha.lower()):
        raise BindingError("runtime image git_sha must be an exact hexadecimal SHA")
    return (
        f"{build_run_url}#artifact=runtime-image-set-{git_sha.lower()}"
        "/container-image-set.json"
    )


def validate_binding(
    evidence: dict[str, Any],
    frozen: dict[str, Any],
    *,
    expected_run_id: str | None = None,
) -> dict[str, Any]:
    if frozen.get("schema_version") != 1 or frozen.get("kind") != "LUMI_RUNTIME_IMAGE_SET_V1":
        raise BindingError("frozen runtime image set schema/kind mismatch")
    evidence_rc = evidence.get("release_candidate")
    frozen_rc = frozen.get("release_candidate")
    if not isinstance(evidence_rc, dict) or not isinstance(frozen_rc, dict):
        raise BindingError("release_candidate missing from evidence or runtime image set")

    evidence_sha = evidence_rc.get("git_sha")
    frozen_sha = frozen_rc.get("git_sha")
    if not isinstance(evidence_sha, str) or evidence_sha.lower() != frozen_sha:
        raise BindingError("staging evidence RC SHA does not equal frozen runtime image-set SHA")
    if evidence_rc.get("version") != frozen_rc.get("version"):
        raise BindingError("staging evidence RC version does not equal frozen runtime image-set version")

    build_run_url = frozen.get("build_run_url")
    if not isinstance(build_run_url, str):
        raise BindingError("frozen runtime image set build_run_url missing")
    build_run_id = _run_id_from_url(build_run_url)
    if expected_run_id is not None and build_run_id != _validate_run_id(expected_run_id):
        raise BindingError("downloaded runtime image set does not originate from requested build run id")
    expected_ref = expected_image_set_ref(build_run_url=build_run_url, git_sha=evidence_sha)
    if evidence_rc.get("container_image_set_ref") != expected_ref:
        raise BindingError("release_candidate.container_image_set_ref does not bind the frozen build artifact")

    frozen_set = frozen.get("container_image_set")
    evidence_set = evidence.get("container_image_set")
    if not isinstance(frozen_set, dict) or not isinstance(evidence_set, dict):
        raise BindingError("container_image_set missing from evidence or frozen artifact")
    if evidence_set != frozen_set:
        raise BindingError("staging evidence container_image_set differs from frozen build artifact")

    gate = _load_gate()
    normalized, blockers = gate.validate_container_image_set(evidence)
    if blockers:
        raise BindingError("NODE-71 container image set blocked: " + "; ".join(blockers))
    if normalized != frozen_set:
        raise BindingError("frozen runtime image set is not NODE-71 canonical after normalization")

    images = normalized.get("images")
    provenance = normalized.get("provenance")
    if not isinstance(images, dict) or set(images) != REQUIRED_RUNTIMES:
        raise BindingError("bound image set does not contain exactly six runtime images")
    if not isinstance(provenance, dict) or set(provenance) != REQUIRED_RUNTIMES:
        raise BindingError("bound image set does not contain exactly six provenance records")

    return {
        "status": "PASS",
        "git_sha": evidence_sha.lower(),
        "version": evidence_rc.get("version"),
        "build_run_id": build_run_id,
        "container_image_set_ref": expected_ref,
        "runtime_count": 6,
    }


def _fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_json(RUNTIME_MANIFEST)
    runtimes = manifest.get("runtimes")
    if not isinstance(runtimes, dict) or set(runtimes) != REQUIRED_RUNTIMES:
        raise BindingError("runtime manifest fixture does not contain exactly six runtimes")
    git_sha = "a" * 40
    version = "1.0.0-rc.binding"
    run_url = "https://github.com/example/lumi/actions/runs/123"
    images: dict[str, str] = {}
    provenance: dict[str, dict[str, Any]] = {}
    for index, service in enumerate(sorted(REQUIRED_RUNTIMES), start=1):
        digest = f"{index:x}" * 64
        image = f"ghcr.io/example/lumi-{service}@sha256:{digest}"
        item = runtimes[service]
        if not isinstance(item, dict):
            raise BindingError(f"runtime fixture entry missing: {service}")
        images[service] = image
        provenance[service] = {
            "git_sha": git_sha,
            "build_recipe_ref": item["dockerfile"],
            "entrypoint": item["entrypoint"],
            "sbom_ref": f"oci://{image}#attestation=sbom",
            "provenance_ref": f"https://github.com/example/lumi/attestations/{index}",
            "source_paths": list(item["source_paths"]),
        }
    image_set = {"images": images, "provenance": provenance}
    ref = expected_image_set_ref(build_run_url=run_url, git_sha=git_sha)
    evidence = {
        "release_candidate": {
            "git_sha": git_sha,
            "version": version,
            "container_image_set_ref": ref,
        },
        "container_image_set": copy.deepcopy(image_set),
    }
    frozen = {
        "schema_version": 1,
        "kind": "LUMI_RUNTIME_IMAGE_SET_V1",
        "release_candidate": {"git_sha": git_sha, "version": version},
        "build_run_url": run_url,
        "container_image_set": copy.deepcopy(image_set),
    }
    return evidence, frozen


def _must_block(
    evidence: dict[str, Any],
    frozen: dict[str, Any],
    label: str,
    *,
    expected_run_id: str | None = "123",
) -> None:
    try:
        validate_binding(evidence, frozen, expected_run_id=expected_run_id)
    except BindingError:
        return
    raise BindingError(f"negative drill did not block: {label}")


def self_test() -> dict[str, Any]:
    evidence, frozen = _fixture()
    clean = validate_binding(evidence, frozen, expected_run_id="123")

    digest_swap = copy.deepcopy(evidence)
    digest_swap["container_image_set"]["images"]["api"] = (
        "ghcr.io/example/lumi-api@sha256:" + "f" * 64
    )
    _must_block(digest_swap, frozen, "digest swap")

    sha_swap = copy.deepcopy(evidence)
    sha_swap["release_candidate"]["git_sha"] = "b" * 40
    _must_block(sha_swap, frozen, "RC SHA swap")

    version_swap = copy.deepcopy(evidence)
    version_swap["release_candidate"]["version"] = "different"
    _must_block(version_swap, frozen, "RC version swap")

    ref_swap = copy.deepcopy(evidence)
    ref_swap["release_candidate"]["container_image_set_ref"] = "https://example.com/other"
    _must_block(ref_swap, frozen, "artifact ref swap")

    provenance_swap = copy.deepcopy(evidence)
    provenance_swap["container_image_set"]["provenance"]["api"]["provenance_ref"] = (
        "https://github.com/example/lumi/attestations/999"
    )
    _must_block(provenance_swap, frozen, "provenance swap")

    _must_block(evidence, frozen, "requested run id swap", expected_run_id="999")

    build_run_swap = copy.deepcopy(frozen)
    build_run_swap["build_run_url"] = "https://github.com/example/lumi/actions/runs/999"
    _must_block(evidence, build_run_swap, "frozen build run URL swap")

    malformed_run_url = copy.deepcopy(frozen)
    malformed_run_url["build_run_url"] = "https://github.com/example/lumi/actions/runs/123?x=1"
    _must_block(evidence, malformed_run_url, "non-canonical build run URL")

    return {
        "status": "PASS",
        "clean": clean,
        "negative_drills": [
            "digest_swap_blocked",
            "rc_sha_swap_blocked",
            "rc_version_swap_blocked",
            "artifact_ref_swap_blocked",
            "provenance_swap_blocked",
            "requested_run_id_swap_blocked",
            "frozen_build_run_url_swap_blocked",
            "noncanonical_build_run_url_blocked",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind NODE-71 evidence to one frozen runtime image build")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--image-set", type=Path)
    parser.add_argument("--expected-run-id")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    if args.evidence is None or args.image_set is None or args.expected_run_id is None:
        raise BindingError(
            "--evidence, --image-set and --expected-run-id are required unless --self-test is used"
        )
    result = validate_binding(
        _load_json(args.evidence),
        _load_json(args.image_set),
        expected_run_id=args.expected_run_id,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BindingError as exc:
        raise SystemExit(f"staging runtime image binding failed: {exc}") from exc

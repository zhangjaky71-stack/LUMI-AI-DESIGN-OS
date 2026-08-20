#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
STAGING_GATE = ROOT / "scripts" / "staging-acceptance-gate.py"
RUNTIME_IMAGE_SET_MODULE = ROOT / "scripts" / "runtime_image_set.py"
RUNTIME_MANIFEST = ROOT / "production" / "runtime-images" / "manifest-v1.json"
REQUIRED_RUNTIMES = {
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
}
SHA256 = frozenset("0123456789abcdef")


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


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BindingError(f"unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_gate() -> ModuleType:
    return _load_module(STAGING_GATE, "lumi_staging_acceptance_gate")


def _load_image_set_module() -> ModuleType:
    return _load_module(RUNTIME_IMAGE_SET_MODULE, "lumi_runtime_image_set")


def _validate_run_id(value: str) -> str:
    if not value.isdecimal() or int(value) <= 0:
        raise BindingError("runtime image build run id must be a positive decimal GitHub Actions run id")
    return value


def _run_identity(build_run_url: str) -> tuple[str, str]:
    parsed = urlsplit(build_run_url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.query or parsed.fragment:
        raise BindingError("runtime image build_run_url must be a canonical github.com HTTPS run URL")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 5 or parts[2:4] != ["actions", "runs"]:
        raise BindingError("runtime image build_run_url must use /<owner>/<repo>/actions/runs/<id>")
    return f"{parts[0]}/{parts[1]}", _validate_run_id(parts[4])


def expected_image_set_ref(*, build_run_url: str, git_sha: str) -> str:
    _run_identity(build_run_url)
    if len(git_sha) != 40 or any(char not in "0123456789abcdef" for char in git_sha.lower()):
        raise BindingError("runtime image git_sha must be an exact hexadecimal SHA")
    return (
        f"{build_run_url}#artifact=runtime-image-set-{git_sha.lower()}"
        "/container-image-set.json"
    )


def _validate_report_binding(
    *,
    frozen: dict[str, Any],
    images: dict[str, str],
    attestation_report: dict[str, Any],
    attestation_report_sha256: str,
    expected_repository: str,
) -> None:
    if len(attestation_report_sha256) != 64 or any(c not in SHA256 for c in attestation_report_sha256):
        raise BindingError("attestation verification report SHA-256 is invalid")
    metadata = frozen.get("attestation_verification")
    if not isinstance(metadata, dict):
        raise BindingError("frozen runtime image set is missing attestation_verification metadata")
    required_metadata = {
        "schema_version",
        "kind",
        "status",
        "runtime_count",
        "repository",
        "report_file",
        "sha256",
    }
    if set(metadata) != required_metadata:
        raise BindingError("frozen attestation_verification metadata shape is invalid")
    if metadata.get("report_file") != "attestation-verification.json":
        raise BindingError("frozen runtime image set binds an unexpected attestation report filename")
    if metadata.get("sha256") != attestation_report_sha256:
        raise BindingError("downloaded attestation verification report SHA-256 differs from frozen image set")
    if metadata.get("repository") != expected_repository:
        raise BindingError("frozen attestation verification repository differs from build-run repository")

    module = _load_image_set_module()
    try:
        summary = module.validate_attestation_report(attestation_report, images=images)
    except Exception as exc:
        raise BindingError(f"downloaded attestation verification report is invalid: {exc}") from exc
    for key in ("schema_version", "kind", "status", "runtime_count", "repository"):
        if metadata.get(key) != summary.get(key):
            raise BindingError(f"frozen attestation verification metadata mismatch: {key}")
    if summary.get("repository") != expected_repository:
        raise BindingError("attestation verification report repository differs from build-run repository")


def validate_binding(
    evidence: dict[str, Any],
    frozen: dict[str, Any],
    attestation_report: dict[str, Any],
    attestation_report_sha256: str,
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
    build_repository, build_run_id = _run_identity(build_run_url)
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

    _validate_report_binding(
        frozen=frozen,
        images=images,
        attestation_report=attestation_report,
        attestation_report_sha256=attestation_report_sha256,
        expected_repository=build_repository,
    )

    return {
        "status": "PASS",
        "git_sha": evidence_sha.lower(),
        "version": evidence_rc.get("version"),
        "build_run_id": build_run_id,
        "container_image_set_ref": expected_ref,
        "attestation_report_sha256": attestation_report_sha256,
        "runtime_count": 6,
    }


def _fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
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
    report = {
        "schema_version": 1,
        "kind": "LUMI_RUNTIME_IMAGE_ATTESTATION_VERIFICATION_V1",
        "status": "PASS",
        "repository": "example/lumi",
        "runtime_count": 6,
        "tools": {
            "docker_buildx": "github.com/docker/buildx v0.contract",
            "github_cli": "gh version 0.contract",
        },
        "results": [
            {
                "service": service,
                "image": images[service],
                "registry_resolvable": True,
                "github_attestation_verified": True,
                "github_attestation_output_lines": 1,
                "buildkit_provenance": {
                    "build_type": "https://mobyproject.org/buildkit@v1",
                    "builder_id": "https://github.com/example/lumi/actions/runs/123",
                    "material_count": 1,
                },
                "buildkit_sbom": {"spdx_version": "SPDX-2.3", "package_count": 1},
                "status": "PASS",
            }
            for service in sorted(images)
        ],
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
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
        "attestation_verification": {
            "schema_version": 1,
            "kind": "LUMI_RUNTIME_IMAGE_ATTESTATION_VERIFICATION_V1",
            "status": "PASS",
            "runtime_count": 6,
            "repository": "example/lumi",
            "report_file": "attestation-verification.json",
            "sha256": report_hash,
        },
        "container_image_set": copy.deepcopy(image_set),
    }
    return evidence, frozen, report, report_hash


def _must_block(
    evidence: dict[str, Any],
    frozen: dict[str, Any],
    report: dict[str, Any],
    report_hash: str,
    label: str,
    *,
    expected_run_id: str | None = "123",
) -> None:
    try:
        validate_binding(
            evidence,
            frozen,
            report,
            report_hash,
            expected_run_id=expected_run_id,
        )
    except BindingError:
        return
    raise BindingError(f"negative drill did not block: {label}")


def self_test() -> dict[str, Any]:
    evidence, frozen, report, report_hash = _fixture()
    clean = validate_binding(
        evidence,
        frozen,
        report,
        report_hash,
        expected_run_id="123",
    )

    digest_swap = copy.deepcopy(evidence)
    digest_swap["container_image_set"]["images"]["api"] = (
        "ghcr.io/example/lumi-api@sha256:" + "f" * 64
    )
    _must_block(digest_swap, frozen, report, report_hash, "digest swap")

    sha_swap = copy.deepcopy(evidence)
    sha_swap["release_candidate"]["git_sha"] = "b" * 40
    _must_block(sha_swap, frozen, report, report_hash, "RC SHA swap")

    version_swap = copy.deepcopy(evidence)
    version_swap["release_candidate"]["version"] = "different"
    _must_block(version_swap, frozen, report, report_hash, "RC version swap")

    ref_swap = copy.deepcopy(evidence)
    ref_swap["release_candidate"]["container_image_set_ref"] = "https://example.com/other"
    _must_block(ref_swap, frozen, report, report_hash, "artifact ref swap")

    provenance_swap = copy.deepcopy(evidence)
    provenance_swap["container_image_set"]["provenance"]["api"]["provenance_ref"] = (
        "https://github.com/example/lumi/attestations/999"
    )
    _must_block(provenance_swap, frozen, report, report_hash, "provenance swap")

    _must_block(evidence, frozen, report, report_hash, "requested run id swap", expected_run_id="999")

    build_run_swap = copy.deepcopy(frozen)
    build_run_swap["build_run_url"] = "https://github.com/example/lumi/actions/runs/999"
    _must_block(evidence, build_run_swap, report, report_hash, "frozen build run URL swap")

    malformed_run_url = copy.deepcopy(frozen)
    malformed_run_url["build_run_url"] = "https://github.com/example/lumi/actions/runs/123?x=1"
    _must_block(evidence, malformed_run_url, report, report_hash, "non-canonical build run URL")

    hash_swap = copy.deepcopy(frozen)
    hash_swap["attestation_verification"]["sha256"] = "f" * 64
    _must_block(evidence, hash_swap, report, report_hash, "attestation report hash swap")

    report_status_swap = copy.deepcopy(report)
    report_status_swap["status"] = "FAIL"
    _must_block(evidence, frozen, report_status_swap, report_hash, "attestation report status swap")

    report_image_swap = copy.deepcopy(report)
    report_image_swap["results"][0]["image"] = "ghcr.io/example/swapped@sha256:" + "f" * 64
    _must_block(evidence, frozen, report_image_swap, report_hash, "attestation report image swap")

    report_repository_swap = copy.deepcopy(report)
    report_repository_swap["repository"] = "example/other"
    _must_block(evidence, frozen, report_repository_swap, report_hash, "attestation report repository swap")

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
            "attestation_report_hash_swap_blocked",
            "attestation_report_status_swap_blocked",
            "attestation_report_image_swap_blocked",
            "attestation_report_repository_swap_blocked",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind NODE-71 evidence to one frozen and verified runtime image build")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--image-set", type=Path)
    parser.add_argument("--attestation-report", type=Path)
    parser.add_argument("--expected-run-id")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    if (
        args.evidence is None
        or args.image_set is None
        or args.attestation_report is None
        or args.expected_run_id is None
    ):
        raise BindingError(
            "--evidence, --image-set, --attestation-report and --expected-run-id are required unless --self-test is used"
        )
    report_bytes = args.attestation_report.read_bytes()
    result = validate_binding(
        _load_json(args.evidence),
        _load_json(args.image_set),
        _load_json(args.attestation_report),
        hashlib.sha256(report_bytes).hexdigest(),
        expected_run_id=args.expected_run_id,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BindingError, OSError) as exc:
        raise SystemExit(f"staging runtime image binding failed: {exc}") from exc

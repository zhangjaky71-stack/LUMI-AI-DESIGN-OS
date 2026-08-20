#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "production" / "runtime-images" / "manifest-v1.json"
STAGING_GATE = ROOT / "scripts" / "staging-acceptance-gate.py"
REQUIRED_RUNTIMES = {
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
}
ATTESTATION_KIND = "LUMI_RUNTIME_IMAGE_ATTESTATION_VERIFICATION_V1"
ATTESTATION_REPORT_FILE = "attestation-verification.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
DIGEST_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class RuntimeImageSetError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeImageSetError(f"unable to read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeImageSetError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "PENDING"


def _load_staging_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_staging_acceptance_gate", STAGING_GATE)
    if spec is None or spec.loader is None:
        raise RuntimeImageSetError("unable to load staging acceptance gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_manifest(path: Path) -> dict[str, Any]:
    manifest = _load_json(path)
    if manifest.get("schema_version") != 1:
        raise RuntimeImageSetError("runtime image manifest schema_version must be 1")
    if manifest.get("registry") != "ghcr.io":
        raise RuntimeImageSetError("runtime image manifest registry must be ghcr.io")
    if not _nonempty(manifest.get("package_base")):
        raise RuntimeImageSetError("runtime image manifest package_base is required")

    runtimes = manifest.get("runtimes")
    if not isinstance(runtimes, dict) or set(runtimes) != REQUIRED_RUNTIMES:
        raise RuntimeImageSetError(
            f"runtime image manifest must define exactly {sorted(REQUIRED_RUNTIMES)}"
        )

    for service in sorted(REQUIRED_RUNTIMES):
        item = runtimes.get(service)
        if not isinstance(item, dict):
            raise RuntimeImageSetError(f"runtime manifest entry missing: {service}")
        dockerfile = item.get("dockerfile")
        entrypoint = item.get("entrypoint")
        source_paths = item.get("source_paths")
        if not _nonempty(dockerfile) or not (ROOT / str(dockerfile)).is_file():
            raise RuntimeImageSetError(f"{service} Dockerfile is missing")
        if not _nonempty(entrypoint):
            raise RuntimeImageSetError(f"{service} entrypoint is missing")
        if not isinstance(source_paths, list) or not source_paths:
            raise RuntimeImageSetError(f"{service} source_paths must be non-empty")
        if len(source_paths) != len(set(source_paths)):
            raise RuntimeImageSetError(f"{service} source_paths contain duplicates")
        for source in source_paths:
            if not _nonempty(source) or not (ROOT / str(source)).exists():
                raise RuntimeImageSetError(f"{service} source path is missing: {source}")

        docker_text = (ROOT / str(dockerfile)).read_text(encoding="utf-8")
        for marker in (
            "python:3.12-slim",
            "uv sync --all-packages --frozen --no-dev",
            "USER 10001:10001",
        ):
            if marker not in docker_text:
                raise RuntimeImageSetError(f"{service} Dockerfile missing {marker}")
        entry_tokens = str(entrypoint).split()
        if not all(token in docker_text for token in entry_tokens):
            raise RuntimeImageSetError(
                f"{service} Dockerfile does not contain declared entrypoint tokens"
            )

    gate = _load_staging_gate()
    api_sources = set(runtimes["api"]["source_paths"])
    model_sources = set(runtimes["model-gateway"]["source_paths"])
    worker_sources = set(runtimes["worker-media"]["source_paths"])
    required_sets = (
        ("api", set(gate.API_REQUIRED_SOURCE_PATHS), api_sources),
        ("model-gateway", set(gate.MODEL_GATEWAY_REQUIRED_SOURCE_PATHS), model_sources),
        ("worker-media", set(gate.WORKER_MEDIA_REQUIRED_SOURCE_PATHS), worker_sources),
    )
    for service, required, supplied in required_sets:
        missing = sorted(required - supplied)
        if missing:
            raise RuntimeImageSetError(
                f"{service} manifest provenance sources missing: {', '.join(missing)}"
            )
    return manifest


def build_fragment(
    *,
    manifest: dict[str, Any],
    service: str,
    image: str,
    git_sha: str,
    sbom_ref: str,
    provenance_ref: str,
    build_run_url: str,
) -> dict[str, Any]:
    if service not in REQUIRED_RUNTIMES:
        raise RuntimeImageSetError(f"unknown runtime service: {service}")
    if not SHA40.fullmatch(git_sha.lower()):
        raise RuntimeImageSetError("git_sha must be an exact 40-character SHA")
    if not DIGEST_IMAGE.fullmatch(image):
        raise RuntimeImageSetError("image must be pinned by immutable @sha256 digest")
    for label, value in (
        ("sbom_ref", sbom_ref),
        ("provenance_ref", provenance_ref),
        ("build_run_url", build_run_url),
    ):
        if not _nonempty(value):
            raise RuntimeImageSetError(f"{label} is required")

    item = manifest["runtimes"][service]
    return {
        "schema_version": 1,
        "service": service,
        "image": image,
        "provenance": {
            "git_sha": git_sha.lower(),
            "build_recipe_ref": item["dockerfile"],
            "entrypoint": item["entrypoint"],
            "sbom_ref": sbom_ref,
            "provenance_ref": provenance_ref,
            "source_paths": list(item["source_paths"]),
        },
        "build_run_url": build_run_url,
    }


def validate_attestation_report(
    report: dict[str, Any],
    *,
    images: dict[str, str],
) -> dict[str, Any]:
    if report.get("schema_version") != 1 or report.get("kind") != ATTESTATION_KIND:
        raise RuntimeImageSetError("attestation verification report schema/kind mismatch")
    if report.get("status") != "PASS":
        raise RuntimeImageSetError("attestation verification report is not PASS")
    if report.get("runtime_count") != 6:
        raise RuntimeImageSetError("attestation verification report must cover exactly six runtimes")
    repository = report.get("repository")
    if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
        raise RuntimeImageSetError("attestation verification report repository is invalid")
    tools = report.get("tools")
    if not isinstance(tools, dict) or not _nonempty(tools.get("docker_buildx")) or not _nonempty(tools.get("github_cli")):
        raise RuntimeImageSetError("attestation verification report tool identity is incomplete")

    results = report.get("results")
    if not isinstance(results, list) or len(results) != 6:
        raise RuntimeImageSetError("attestation verification report results must contain six entries")
    seen: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            raise RuntimeImageSetError("attestation verification result must be an object")
        service = item.get("service")
        if not isinstance(service, str) or service not in REQUIRED_RUNTIMES or service in seen:
            raise RuntimeImageSetError(f"attestation verification result service invalid/duplicate: {service}")
        seen.add(service)
        if item.get("image") != images.get(service):
            raise RuntimeImageSetError(f"attestation verification image mismatch for {service}")
        if item.get("status") != "PASS":
            raise RuntimeImageSetError(f"attestation verification status is not PASS for {service}")
        if item.get("registry_resolvable") is not True:
            raise RuntimeImageSetError(f"registry digest was not verified for {service}")
        if item.get("github_attestation_verified") is not True:
            raise RuntimeImageSetError(f"GitHub artifact attestation was not verified for {service}")
        provenance = item.get("buildkit_provenance")
        sbom = item.get("buildkit_sbom")
        if not isinstance(provenance, dict) or not _nonempty(provenance.get("build_type")) or not _nonempty(provenance.get("builder_id")):
            raise RuntimeImageSetError(f"BuildKit provenance summary is missing for {service}")
        if not isinstance(sbom, dict) or not _nonempty(sbom.get("spdx_version")):
            raise RuntimeImageSetError(f"BuildKit SBOM summary is missing for {service}")
    if seen != REQUIRED_RUNTIMES:
        raise RuntimeImageSetError("attestation verification report service set is incomplete")
    return {
        "schema_version": 1,
        "kind": ATTESTATION_KIND,
        "status": "PASS",
        "runtime_count": 6,
        "repository": repository,
    }


def assemble(
    *,
    fragments_dir: Path,
    git_sha: str,
    version: str,
    build_run_url: str,
    attestation_report: Path,
) -> dict[str, Any]:
    if not SHA40.fullmatch(git_sha.lower()):
        raise RuntimeImageSetError("git_sha must be an exact 40-character SHA")
    if not _nonempty(version):
        raise RuntimeImageSetError("version is required")
    if not _nonempty(build_run_url):
        raise RuntimeImageSetError("build_run_url is required")
    if attestation_report.name != ATTESTATION_REPORT_FILE:
        raise RuntimeImageSetError(
            f"attestation report must be named {ATTESTATION_REPORT_FILE}"
        )

    fragments: dict[str, dict[str, Any]] = {}
    for path in sorted(fragments_dir.glob("*.json")):
        fragment = _load_json(path)
        service = fragment.get("service")
        if service in fragments:
            raise RuntimeImageSetError(f"duplicate runtime fragment: {service}")
        if not isinstance(service, str):
            raise RuntimeImageSetError(f"runtime fragment missing service: {path}")
        fragments[service] = fragment
    if set(fragments) != REQUIRED_RUNTIMES:
        raise RuntimeImageSetError(
            f"runtime fragments must cover exactly {sorted(REQUIRED_RUNTIMES)}"
        )

    images: dict[str, str] = {}
    provenance: dict[str, dict[str, Any]] = {}
    for service in sorted(REQUIRED_RUNTIMES):
        fragment = fragments[service]
        image = fragment.get("image")
        item = fragment.get("provenance")
        if not isinstance(image, str) or not DIGEST_IMAGE.fullmatch(image):
            raise RuntimeImageSetError(f"{service} fragment image is not immutable")
        if not isinstance(item, dict) or item.get("git_sha") != git_sha.lower():
            raise RuntimeImageSetError(f"{service} fragment git_sha mismatch")
        if fragment.get("build_run_url") != build_run_url:
            raise RuntimeImageSetError(f"{service} build_run_url mismatch")
        images[service] = image
        provenance[service] = item

    image_set = {"images": images, "provenance": provenance}
    gate = _load_staging_gate()
    normalized, blockers = gate.validate_container_image_set(
        {
            "release_candidate": {"git_sha": git_sha.lower()},
            "container_image_set": image_set,
        }
    )
    if blockers:
        raise RuntimeImageSetError("staging image-set contract blocked: " + "; ".join(blockers))

    report = _load_json(attestation_report)
    report_summary = validate_attestation_report(report, images=images)
    report_sha256 = hashlib.sha256(attestation_report.read_bytes()).hexdigest()
    if not SHA256.fullmatch(report_sha256):
        raise RuntimeImageSetError("attestation report SHA-256 calculation failed")

    return {
        "schema_version": 1,
        "kind": "LUMI_RUNTIME_IMAGE_SET_V1",
        "release_candidate": {
            "git_sha": git_sha.lower(),
            "version": version,
        },
        "build_run_url": build_run_url,
        "attestation_verification": {
            **report_summary,
            "report_file": ATTESTATION_REPORT_FILE,
            "sha256": report_sha256,
        },
        "container_image_set": normalized,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and validate the canonical six-runtime RC image set")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate-manifest")

    fragment = sub.add_parser("fragment")
    fragment.add_argument("--service", required=True)
    fragment.add_argument("--image", required=True)
    fragment.add_argument("--git-sha", required=True)
    fragment.add_argument("--sbom-ref", required=True)
    fragment.add_argument("--provenance-ref", required=True)
    fragment.add_argument("--build-run-url", required=True)
    fragment.add_argument("--out", type=Path, required=True)

    freeze = sub.add_parser("assemble")
    freeze.add_argument("--fragments-dir", type=Path, required=True)
    freeze.add_argument("--git-sha", required=True)
    freeze.add_argument("--version", required=True)
    freeze.add_argument("--build-run-url", required=True)
    freeze.add_argument("--attestation-report", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    manifest = validate_manifest(args.manifest)
    if args.command == "validate-manifest":
        print(json.dumps({"status": "PASS", "runtime_count": len(manifest["runtimes"])}, sort_keys=True))
        return 0
    if args.command == "fragment":
        payload = build_fragment(
            manifest=manifest,
            service=args.service,
            image=args.image,
            git_sha=args.git_sha,
            sbom_ref=args.sbom_ref,
            provenance_ref=args.provenance_ref,
            build_run_url=args.build_run_url,
        )
        _write_json(args.out, payload)
        return 0
    if args.command == "assemble":
        payload = assemble(
            fragments_dir=args.fragments_dir,
            git_sha=args.git_sha,
            version=args.version,
            build_run_url=args.build_run_url,
            attestation_report=args.attestation_report,
        )
        _write_json(args.out, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    raise RuntimeImageSetError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeImageSetError as exc:
        raise SystemExit(f"runtime image set failed: {exc}") from exc

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

IMAGE_REF = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SERVICE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_SERVICES = {
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
}
RELEASE_SOURCE_REF = "refs/heads/release-closure-p0"
SIGNER_WORKFLOW_PATH = ".github/workflows/build-runtime-image-set.yml"


class AttestationVerificationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ImageTarget:
    service: str
    image: str


@dataclass(frozen=True, slots=True)
class GitHubAttestationPolicy:
    repository: str
    signer_workflow: str
    source_digest: str
    source_ref: str
    workflow_ref: str
    deny_self_hosted_runners: bool = True


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AttestationVerificationError(message)


def parse_target(raw: str) -> ImageTarget:
    if "=" not in raw:
        raise AttestationVerificationError("--image must use service=registry/name@sha256:<digest>")
    service, image = raw.split("=", 1)
    _require(bool(SERVICE.fullmatch(service)), f"invalid runtime service name: {service!r}")
    _require(bool(IMAGE_REF.fullmatch(image)), f"runtime image must use an immutable @sha256 digest: {image!r}")
    return ImageTarget(service=service, image=image)


def resolve_github_attestation_policy(
    repository: str,
    env: Mapping[str, str],
) -> GitHubAttestationPolicy:
    _require(bool(REPOSITORY.fullmatch(repository)), "repository must use OWNER/REPO form")
    source_digest = env.get("GITHUB_SHA", "").lower()
    _require(bool(SHA40.fullmatch(source_digest)), "GITHUB_SHA must be an exact lowercase SHA40")

    source_ref = env.get("GITHUB_REF", "")
    _require(
        source_ref == RELEASE_SOURCE_REF,
        f"GITHUB_REF must be the release source ref {RELEASE_SOURCE_REF}",
    )

    signer_workflow = f"{repository}/{SIGNER_WORKFLOW_PATH}"
    workflow_ref = env.get("GITHUB_WORKFLOW_REF", "")
    expected_workflow_ref = f"{signer_workflow}@{source_ref}"
    _require(
        workflow_ref == expected_workflow_ref,
        "GITHUB_WORKFLOW_REF must bind the canonical runtime-image build workflow to the release ref",
    )

    return GitHubAttestationPolicy(
        repository=repository,
        signer_workflow=signer_workflow,
        source_digest=source_digest,
        source_ref=source_ref,
        workflow_ref=workflow_ref,
    )


def _json_value(raw: str, *, label: str) -> Any:
    value = raw.strip()
    _require(bool(value), f"{label} returned empty output")
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise AttestationVerificationError(f"{label} returned invalid JSON: {exc}") from exc


def validate_provenance(value: Any) -> dict[str, Any]:
    _require(isinstance(value, dict) and bool(value), "BuildKit SLSA provenance must be a non-empty object")
    build_type = value.get("buildType")
    builder = value.get("builder")
    _require(isinstance(build_type, str) and bool(build_type.strip()), "BuildKit SLSA provenance buildType is missing")
    _require(isinstance(builder, dict) and bool(builder), "BuildKit SLSA provenance builder is missing")
    builder_id = builder.get("id")
    _require(isinstance(builder_id, str) and bool(builder_id.strip()), "BuildKit SLSA provenance builder.id is missing")
    materials = value.get("materials")
    _require(isinstance(materials, list), "BuildKit SLSA provenance materials must be an array")
    return {
        "build_type": build_type,
        "builder_id": builder_id,
        "material_count": len(materials),
    }


def validate_sbom(value: Any) -> dict[str, Any]:
    _require(isinstance(value, dict) and bool(value), "BuildKit SPDX SBOM must be a non-empty object")
    _require(value.get("SPDXID") == "SPDXRef-DOCUMENT", "SPDX SBOM document identifier is invalid")
    spdx_version = value.get("spdxVersion")
    _require(
        isinstance(spdx_version, str) and spdx_version.startswith("SPDX-"),
        "SPDX SBOM spdxVersion is missing/invalid",
    )
    packages = value.get("packages")
    _require(isinstance(packages, list), "SPDX SBOM packages must be an array")
    return {
        "spdx_version": spdx_version,
        "package_count": len(packages),
    }


def _run(args: Sequence[str], *, label: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise AttestationVerificationError(f"{label} executable is unavailable: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AttestationVerificationError(f"{label} timed out") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise AttestationVerificationError(
            f"{label} failed with exit {result.returncode}: {detail[:2000]}"
        )
    return result


def _tool_version(args: Sequence[str], *, label: str) -> str:
    result = _run(args, label=label)
    first = (result.stdout or result.stderr).strip().splitlines()
    return first[0] if first else "unknown"


def _inspect_json(image: str, expression: str, *, label: str) -> Any:
    result = _run(
        ["docker", "buildx", "imagetools", "inspect", image, "--format", expression],
        label=label,
    )
    return _json_value(result.stdout, label=label)


def _verify_one(
    target: ImageTarget,
    *,
    policy: GitHubAttestationPolicy,
) -> dict[str, Any]:
    image = target.image
    _run(
        ["docker", "buildx", "imagetools", "inspect", image],
        label=f"{target.service} registry digest resolution",
    )
    attestation = _run(
        [
            "gh",
            "attestation",
            "verify",
            f"oci://{image}",
            "--repo",
            policy.repository,
            "--signer-workflow",
            policy.signer_workflow,
            "--source-digest",
            policy.source_digest,
            "--source-ref",
            policy.source_ref,
            "--deny-self-hosted-runners",
        ],
        label=f"{target.service} GitHub artifact attestation signer/source verification",
    )

    provenance = _inspect_json(
        image,
        "{{ json .Provenance.SLSA }}",
        label=f"{target.service} BuildKit SLSA provenance inspection",
    )
    provenance_summary = validate_provenance(provenance)

    sbom = _inspect_json(
        image,
        "{{ json .SBOM.SPDX }}",
        label=f"{target.service} BuildKit SPDX SBOM inspection",
    )
    if sbom is None or sbom == {}:
        sbom = _inspect_json(
            image,
            '{{ json (index .SBOM "linux/amd64").SPDX }}',
            label=f"{target.service} linux/amd64 BuildKit SPDX SBOM inspection",
        )
    sbom_summary = validate_sbom(sbom)

    attestation_lines = [line for line in attestation.stdout.splitlines() if line.strip()]
    return {
        "service": target.service,
        "image": image,
        "registry_resolvable": True,
        "github_attestation_verified": True,
        "github_attestation_output_lines": len(attestation_lines),
        "github_attestation_policy": {
            "signer_workflow": policy.signer_workflow,
            "source_digest": policy.source_digest,
            "source_ref": policy.source_ref,
            "workflow_ref": policy.workflow_ref,
            "deny_self_hosted_runners": policy.deny_self_hosted_runners,
        },
        "buildkit_provenance": provenance_summary,
        "buildkit_sbom": sbom_summary,
        "status": "PASS",
    }


def self_test() -> dict[str, Any]:
    digest = "a" * 64
    good = parse_target(f"api=ghcr.io/example/lumi-api@sha256:{digest}")
    _require(good.service == "api", "clean immutable image fixture did not parse")

    bad_targets = [
        "api=ghcr.io/example/lumi-api:latest",
        "api=ghcr.io/example/lumi-api@sha256:1234",
        f"BAD SERVICE=ghcr.io/example/lumi-api@sha256:{digest}",
        f"ghcr.io/example/lumi-api@sha256:{digest}",
    ]
    for raw in bad_targets:
        try:
            parse_target(raw)
        except AttestationVerificationError:
            continue
        raise AttestationVerificationError(f"negative immutable image-ref drill did not block: {raw}")

    source_digest = "b" * 40
    good_env = {
        "GITHUB_SHA": source_digest,
        "GITHUB_REF": RELEASE_SOURCE_REF,
        "GITHUB_WORKFLOW_REF": (
            "example/lumi/.github/workflows/build-runtime-image-set.yml@"
            + RELEASE_SOURCE_REF
        ),
    }
    policy = resolve_github_attestation_policy("example/lumi", good_env)
    _require(policy.source_digest == source_digest, "clean source digest identity fixture failed")
    _require(
        policy.signer_workflow == "example/lumi/.github/workflows/build-runtime-image-set.yml",
        "clean signer workflow identity fixture failed",
    )

    bad_identity_envs = [
        {**good_env, "GITHUB_SHA": "bad"},
        {**good_env, "GITHUB_REF": "refs/heads/main"},
        {
            **good_env,
            "GITHUB_WORKFLOW_REF": "example/lumi/.github/workflows/other.yml@refs/heads/release-closure-p0",
        },
    ]
    for value in bad_identity_envs:
        try:
            resolve_github_attestation_policy("example/lumi", value)
        except AttestationVerificationError:
            continue
        raise AttestationVerificationError("negative GitHub signer/source identity drill did not block")

    provenance = {
        "buildType": "https://mobyproject.org/buildkit@v1",
        "builder": {"id": "https://github.com/example/repo/actions/runs/1"},
        "materials": [],
    }
    provenance_summary = validate_provenance(provenance)
    _require(provenance_summary["material_count"] == 0, "clean provenance fixture failed")

    bad_provenance = [
        {},
        {"builder": {"id": "builder"}, "materials": []},
        {"buildType": "buildkit", "materials": []},
        {"buildType": "buildkit", "builder": {}, "materials": []},
        {"buildType": "buildkit", "builder": {"id": "builder"}, "materials": {}},
    ]
    for value in bad_provenance:
        try:
            validate_provenance(value)
        except AttestationVerificationError:
            continue
        raise AttestationVerificationError("negative BuildKit provenance drill did not block")

    sbom = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "packages": [],
    }
    sbom_summary = validate_sbom(sbom)
    _require(sbom_summary["package_count"] == 0, "clean SPDX fixture failed")

    bad_sbom = [
        {},
        {"SPDXID": "wrong", "spdxVersion": "SPDX-2.3", "packages": []},
        {"SPDXID": "SPDXRef-DOCUMENT", "spdxVersion": "2.3", "packages": []},
        {"SPDXID": "SPDXRef-DOCUMENT", "spdxVersion": "SPDX-2.3", "packages": {}},
    ]
    for value in bad_sbom:
        try:
            validate_sbom(value)
        except AttestationVerificationError:
            continue
        raise AttestationVerificationError("negative SPDX SBOM drill did not block")

    return {
        "status": "PASS",
        "immutable_ref_negative_drills": len(bad_targets),
        "github_identity_negative_drills": len(bad_identity_envs),
        "provenance_negative_drills": len(bad_provenance),
        "sbom_negative_drills": len(bad_sbom),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify six immutable runtime images, GitHub signer/source attestations, "
            "BuildKit provenance, and SPDX SBOMs"
        )
    )
    parser.add_argument("--repository", help="GitHub repository in OWNER/REPO form")
    parser.add_argument("--image", action="append", default=[], help="service=registry/name@sha256:<digest>")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0

    if not isinstance(args.repository, str) or not REPOSITORY.fullmatch(args.repository):
        raise AttestationVerificationError("--repository must use OWNER/REPO form")
    policy = resolve_github_attestation_policy(args.repository, os.environ)
    targets = [parse_target(raw) for raw in args.image]
    services = [target.service for target in targets]
    _require(len(services) == 6, "exactly six runtime --image values are required")
    _require(len(services) == len(set(services)), "runtime --image services must be unique")
    _require(set(services) == EXPECTED_SERVICES, f"runtime images must cover exactly {sorted(EXPECTED_SERVICES)}")
    _require(shutil.which("docker") is not None, "docker executable is unavailable")
    _require(shutil.which("gh") is not None, "GitHub CLI executable is unavailable")

    results = [_verify_one(target, policy=policy) for target in targets]
    payload = {
        "schema_version": 1,
        "kind": "LUMI_RUNTIME_IMAGE_ATTESTATION_VERIFICATION_V1",
        "status": "PASS",
        "repository": args.repository,
        "runtime_count": len(results),
        "github_attestation_policy": {
            "signer_workflow": policy.signer_workflow,
            "source_digest": policy.source_digest,
            "source_ref": policy.source_ref,
            "workflow_ref": policy.workflow_ref,
            "deny_self_hosted_runners": policy.deny_self_hosted_runners,
        },
        "tools": {
            "docker_buildx": _tool_version(["docker", "buildx", "version"], label="docker buildx version"),
            "github_cli": _tool_version(["gh", "--version"], label="GitHub CLI version"),
        },
        "results": results,
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AttestationVerificationError as exc:
        raise SystemExit(f"runtime image attestation verification failed: {exc}") from exc

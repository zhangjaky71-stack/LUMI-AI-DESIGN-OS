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
EXPECTED_DOCKERFILES = {
    "api": "apps/api/Dockerfile",
    "agent-runtime": "apps/agent-runtime/Dockerfile",
    "model-gateway": "services/model-gateway/Dockerfile",
    "tool-gateway": "services/tool-gateway/Dockerfile",
    "worker-media": "apps/worker-media/Dockerfile",
    "sandbox-runtime": "services/sandbox-runtime/Dockerfile",
}
EXPECTED_SERVICES = set(EXPECTED_DOCKERFILES)
EXPECTED_BASE_IMAGE_PREFIXES = {
    "UV_BASE_IMAGE": "ghcr.io/astral-sh/uv@sha256:",
    "PYTHON_BASE_IMAGE": "python@sha256:",
}
RELEASE_SOURCE_REF = "refs/heads/release-closure-p0"
SIGNER_WORKFLOW_PATH = ".github/workflows/build-runtime-image-set.yml"
BUILDKIT_BUILD_TYPE = "https://mobyproject.org/buildkit@v1"
BUILDKIT_PLATFORM = "linux/amd64"


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


def _validate_base_image_build_args(invocation: Mapping[str, Any]) -> dict[str, str]:
    parameters = invocation.get("parameters")
    _require(isinstance(parameters, dict), "BuildKit SLSA provenance invocation.parameters is missing")
    args = parameters.get("args")
    _require(isinstance(args, dict), "BuildKit SLSA provenance invocation.parameters.args is missing")

    result: dict[str, str] = {}
    for arg_name, prefix in EXPECTED_BASE_IMAGE_PREFIXES.items():
        key = f"build-arg:{arg_name}"
        value = args.get(key)
        _require(isinstance(value, str), f"BuildKit provenance missing {key}")
        _require(
            bool(IMAGE_REF.fullmatch(value)),
            f"BuildKit provenance {key} must be a digest-only OCI image reference",
        )
        _require(
            value.startswith(prefix),
            f"BuildKit provenance {key} must use approved base image repository {prefix.split('@')[0]}",
        )
        result[arg_name] = value
    return result


def validate_provenance(
    value: Any,
    *,
    repository: str,
    source_digest: str,
    dockerfile: str,
) -> dict[str, Any]:
    _require(isinstance(value, dict) and bool(value), "BuildKit SLSA provenance must be a non-empty object")
    _require(
        value.get("buildType") == BUILDKIT_BUILD_TYPE,
        "BuildKit SLSA provenance buildType must be the canonical BuildKit build type",
    )

    builder = value.get("builder")
    _require(isinstance(builder, dict) and bool(builder), "BuildKit SLSA provenance builder is missing")
    builder_id = builder.get("id")
    _require(isinstance(builder_id, str) and bool(builder_id.strip()), "BuildKit SLSA provenance builder.id is missing")

    invocation = value.get("invocation")
    _require(isinstance(invocation, dict), "BuildKit SLSA provenance invocation is missing")
    config_source = invocation.get("configSource")
    _require(isinstance(config_source, dict), "BuildKit SLSA provenance configSource is missing")

    expected_uri = f"https://github.com/{repository}.git#{source_digest}"
    source_uri = config_source.get("uri")
    _require(
        source_uri == expected_uri,
        "BuildKit provenance configSource.uri must bind the immutable GitHub repository and RC SHA",
    )

    source_digests = config_source.get("digest")
    _require(isinstance(source_digests, dict), "BuildKit provenance configSource.digest is missing")
    _require(
        source_digests.get("sha1") == source_digest,
        "BuildKit provenance configSource.digest.sha1 must equal the RC Git SHA",
    )
    _require(
        config_source.get("entryPoint") == dockerfile,
        "BuildKit provenance configSource.entryPoint must equal the runtime Dockerfile",
    )

    environment = invocation.get("environment")
    _require(isinstance(environment, dict), "BuildKit SLSA provenance invocation.environment is missing")
    _require(
        environment.get("platform") == BUILDKIT_PLATFORM,
        "BuildKit provenance invocation.environment.platform must be linux/amd64",
    )

    base_images = _validate_base_image_build_args(invocation)

    materials = value.get("materials")
    _require(
        isinstance(materials, list) and len(materials) > 0,
        "BuildKit SLSA provenance materials must be a non-empty array",
    )
    material_digests = sorted(
        {
            digest
            for material in materials
            if isinstance(material, dict)
            for digest_map in [material.get("digest")]
            if isinstance(digest_map, dict)
            for digest in [digest_map.get("sha256")]
            if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
        }
    )
    _require(material_digests, "BuildKit SLSA provenance materials must include immutable SHA-256 dependencies")

    return {
        "build_type": BUILDKIT_BUILD_TYPE,
        "builder_id": builder_id,
        "source_uri": source_uri,
        "source_digest": source_digest,
        "entrypoint": dockerfile,
        "platform": BUILDKIT_PLATFORM,
        "base_images": base_images,
        "material_count": len(materials),
        "material_sha256_count": len(material_digests),
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
    provenance_summary = validate_provenance(
        provenance,
        repository=policy.repository,
        source_digest=policy.source_digest,
        dockerfile=EXPECTED_DOCKERFILES[target.service],
    )

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
        "buildType": BUILDKIT_BUILD_TYPE,
        "builder": {"id": "https://github.com/example/repo/actions/runs/1"},
        "invocation": {
            "configSource": {
                "uri": f"https://github.com/example/lumi.git#{source_digest}",
                "digest": {"sha1": source_digest},
                "entryPoint": "apps/api/Dockerfile",
            },
            "parameters": {
                "args": {
                    "build-arg:UV_BASE_IMAGE": f"ghcr.io/astral-sh/uv@sha256:{'c' * 64}",
                    "build-arg:PYTHON_BASE_IMAGE": f"python@sha256:{'d' * 64}",
                }
            },
            "environment": {"platform": BUILDKIT_PLATFORM},
        },
        "materials": [
            {
                "uri": "pkg:docker/python@3.12-slim",
                "digest": {"sha256": "e" * 64},
            }
        ],
    }
    provenance_summary = validate_provenance(
        provenance,
        repository="example/lumi",
        source_digest=source_digest,
        dockerfile="apps/api/Dockerfile",
    )
    _require(provenance_summary["material_count"] == 1, "clean provenance fixture failed")
    _require(
        provenance_summary["base_images"]["UV_BASE_IMAGE"].startswith("ghcr.io/astral-sh/uv@sha256:"),
        "clean digest-pinned uv base image fixture failed",
    )

    bad_provenance = [
        {},
        {**provenance, "buildType": "buildkit"},
        {**provenance, "builder": {}},
        {**provenance, "invocation": {}},
        {
            **provenance,
            "invocation": {
                **provenance["invocation"],
                "configSource": {
                    **provenance["invocation"]["configSource"],
                    "uri": f"https://github.com/example/other.git#{source_digest}",
                },
            },
        },
        {
            **provenance,
            "invocation": {
                **provenance["invocation"],
                "configSource": {
                    **provenance["invocation"]["configSource"],
                    "digest": {"sha1": "f" * 40},
                },
            },
        },
        {
            **provenance,
            "invocation": {
                **provenance["invocation"],
                "configSource": {
                    **provenance["invocation"]["configSource"],
                    "entryPoint": "Dockerfile",
                },
            },
        },
        {
            **provenance,
            "invocation": {
                **provenance["invocation"],
                "environment": {"platform": "linux/arm64"},
            },
        },
        {
            **provenance,
            "invocation": {
                **provenance["invocation"],
                "parameters": {
                    "args": {
                        "build-arg:UV_BASE_IMAGE": "ghcr.io/astral-sh/uv:0.11.28",
                        "build-arg:PYTHON_BASE_IMAGE": f"python@sha256:{'d' * 64}",
                    }
                },
            },
        },
        {
            **provenance,
            "invocation": {
                **provenance["invocation"],
                "parameters": {
                    "args": {
                        "build-arg:UV_BASE_IMAGE": f"ghcr.io/other/uv@sha256:{'c' * 64}",
                        "build-arg:PYTHON_BASE_IMAGE": f"python@sha256:{'d' * 64}",
                    }
                },
            },
        },
        {
            **provenance,
            "invocation": {
                **provenance["invocation"],
                "parameters": {
                    "args": {
                        "build-arg:UV_BASE_IMAGE": f"ghcr.io/astral-sh/uv@sha256:{'c' * 64}",
                        "build-arg:PYTHON_BASE_IMAGE": "python:3.12-slim",
                    }
                },
            },
        },
        {**provenance, "materials": []},
        {
            **provenance,
            "materials": [{"uri": "https://example.invalid/source", "digest": {"sha1": "a" * 40}}],
        },
    ]
    for value in bad_provenance:
        try:
            validate_provenance(
                value,
                repository="example/lumi",
                source_digest=source_digest,
                dockerfile="apps/api/Dockerfile",
            )
        except AttestationVerificationError:
            continue
        raise AttestationVerificationError("negative immutable BuildKit provenance drill did not block")

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
            "BuildKit immutable Git/base-image provenance, and SPDX SBOMs"
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

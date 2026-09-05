#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "runtime_image_set.py"


class ContractError(RuntimeError):
    pass


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_runtime_image_set", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ContractError("unable to import runtime_image_set.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expect_failure(fn: object, label: str) -> None:
    try:
        fn()  # type: ignore[operator]
    except Exception:
        return
    raise ContractError(f"negative drill did not block: {label}")


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _attestation_report(
    images: dict[str, str],
    git_sha: str,
    manifest: dict[str, object],
) -> dict[str, object]:
    policy = {
        "signer_workflow": "example/lumi/.github/workflows/build-runtime-image-set.yml",
        "source_digest": git_sha,
        "source_ref": "refs/heads/release-closure-p0",
        "workflow_ref": (
            "example/lumi/.github/workflows/build-runtime-image-set.yml@"
            "refs/heads/release-closure-p0"
        ),
        "deny_self_hosted_runners": True,
    }
    base_images = {
        "UV_BASE_IMAGE": "ghcr.io/astral-sh/uv@sha256:" + "b" * 64,
        "PYTHON_BASE_IMAGE": "python@sha256:" + "c" * 64,
    }
    runtimes = manifest["runtimes"]
    if not isinstance(runtimes, dict):
        raise ContractError("manifest runtimes missing")
    results: list[dict[str, object]] = []
    for service in sorted(images):
        runtime = runtimes.get(service)
        if not isinstance(runtime, dict):
            raise ContractError(f"manifest runtime missing: {service}")
        dockerfile = runtime.get("dockerfile")
        if not isinstance(dockerfile, str):
            raise ContractError(f"manifest Dockerfile missing: {service}")
        results.append(
            {
                "service": service,
                "image": images[service],
                "registry_resolvable": True,
                "github_attestation_verified": True,
                "github_attestation_output_lines": 1,
                "github_attestation_policy": dict(policy),
                "buildkit_provenance": {
                    "build_type": "https://mobyproject.org/buildkit@v1",
                    "builder_id": "https://github.com/example/lumi/actions/runs/123",
                    "source_uri": f"https://github.com/example/lumi.git#{git_sha}",
                    "source_digest": git_sha,
                    "entrypoint": dockerfile,
                    "platform": "linux/amd64",
                    "base_images": dict(base_images),
                    "material_count": 3,
                    "material_sha256_count": 2,
                },
                "buildkit_sbom": {
                    "spdx_version": "SPDX-2.3",
                    "package_count": 1,
                },
                "status": "PASS",
            }
        )
    return {
        "schema_version": 1,
        "kind": "LUMI_RUNTIME_IMAGE_ATTESTATION_VERIFICATION_V1",
        "status": "PASS",
        "repository": "example/lumi",
        "runtime_count": 6,
        "github_attestation_policy": dict(policy),
        "tools": {
            "docker_buildx": "github.com/docker/buildx v0.contract",
            "github_cli": "gh version 0.contract",
        },
        "results": results,
    }


def _assemble(
    module: ModuleType,
    *,
    fragments: Path,
    git_sha: str,
    version: str,
    run_url: str,
    report_path: Path,
) -> dict[str, object]:
    return module.assemble(
        fragments_dir=fragments,
        git_sha=git_sha,
        version=version,
        build_run_url=run_url,
        attestation_report=report_path,
    )


def main() -> int:
    module = _load_module()
    manifest = module.validate_manifest(module.DEFAULT_MANIFEST)
    git_sha = "a" * 40
    version = "1.0.0-rc.contract"
    run_url = "https://github.com/example/lumi/actions/runs/123"

    with tempfile.TemporaryDirectory(prefix="lumi-runtime-image-set-") as tmp:
        root = Path(tmp)
        fragments = root / "fragments"
        fragments.mkdir()
        images: dict[str, str] = {}

        for index, service in enumerate(sorted(module.REQUIRED_RUNTIMES), start=1):
            digest = f"{index:x}" * 64
            image = f"ghcr.io/example/lumi-{service}@sha256:{digest}"
            images[service] = image
            fragment = module.build_fragment(
                manifest=manifest,
                service=service,
                image=image,
                git_sha=git_sha,
                sbom_ref=f"oci://{image}#attestation=sbom",
                provenance_ref=f"https://github.com/example/lumi/attestations/{index}",
                build_run_url=run_url,
            )
            _write(fragments / f"{service}.json", fragment)

        report_path = root / "attestation-verification.json"
        report = _attestation_report(images, git_sha, manifest)
        _write(report_path, report)

        clean = _assemble(
            module,
            fragments=fragments,
            git_sha=git_sha,
            version=version,
            run_url=run_url,
            report_path=report_path,
        )
        image_set = clean.get("container_image_set")
        if not isinstance(image_set, dict):
            raise ContractError("clean assembly missing container_image_set")
        frozen_images = image_set.get("images")
        provenance = image_set.get("provenance")
        if not isinstance(frozen_images, dict) or set(frozen_images) != set(module.REQUIRED_RUNTIMES):
            raise ContractError("clean assembly did not freeze exactly six images")
        if not isinstance(provenance, dict) or set(provenance) != set(module.REQUIRED_RUNTIMES):
            raise ContractError("clean assembly did not freeze exactly six provenance records")
        if any("@sha256:" not in str(value) for value in frozen_images.values()):
            raise ContractError("clean assembly contains a mutable image reference")
        attestation = clean.get("attestation_verification")
        if not isinstance(attestation, dict):
            raise ContractError("clean assembly missing attestation_verification binding")
        if attestation.get("status") != "PASS" or attestation.get("runtime_count") != 6:
            raise ContractError("clean assembly attestation binding is not PASS for six runtimes")
        if attestation.get("source_digest") != git_sha:
            raise ContractError("clean assembly did not bind attestation source digest to RC git_sha")
        base_images = attestation.get("base_images")
        if not isinstance(base_images, dict) or set(base_images) != {
            "UV_BASE_IMAGE",
            "PYTHON_BASE_IMAGE",
        }:
            raise ContractError("clean assembly did not freeze the common base-image identities")
        if not all("@sha256:" in str(value) for value in base_images.values()):
            raise ContractError("clean assembly froze a mutable base-image identity")
        report_hash = attestation.get("sha256")
        if not isinstance(report_hash, str) or len(report_hash) != 64:
            raise ContractError("clean assembly did not bind attestation report SHA-256")
        if attestation.get("report_file") != "attestation-verification.json":
            raise ContractError("clean assembly did not bind canonical attestation report file")

        missing = fragments / "api.json"
        saved_api = json.loads(missing.read_text(encoding="utf-8"))
        missing.unlink()
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "missing runtime fragment",
        )
        _write(missing, saved_api)

        mutable = copy.deepcopy(saved_api)
        mutable["image"] = "ghcr.io/example/lumi-api:latest"
        _write(missing, mutable)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "mutable image tag",
        )
        _write(missing, saved_api)

        wrong_sha = copy.deepcopy(saved_api)
        wrong_sha["provenance"]["git_sha"] = "b" * 40
        _write(missing, wrong_sha)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "provenance SHA mismatch",
        )
        _write(missing, saved_api)

        wrong_run = copy.deepcopy(saved_api)
        wrong_run["build_run_url"] = "https://github.com/example/lumi/actions/runs/999"
        _write(missing, wrong_run)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "mixed build-run provenance",
        )
        _write(missing, saved_api)

        report_path.unlink()
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "missing attestation verification report",
        )
        _write(report_path, report)

        failed_report = copy.deepcopy(report)
        failed_report["status"] = "FAIL"
        _write(report_path, failed_report)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "failed attestation verification report",
        )

        image_swap_report = copy.deepcopy(report)
        image_swap_report["results"][0]["image"] = (  # type: ignore[index]
            "ghcr.io/example/swapped@sha256:" + "f" * 64
        )
        _write(report_path, image_swap_report)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "attestation report image mismatch",
        )

        stale_source_report = copy.deepcopy(report)
        stale_source_report["github_attestation_policy"]["source_digest"] = "b" * 40  # type: ignore[index]
        _write(report_path, stale_source_report)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "stale attestation source digest",
        )

        mixed_policy_report = copy.deepcopy(report)
        mixed_policy_report["results"][0]["github_attestation_policy"]["source_digest"] = "b" * 40  # type: ignore[index]
        _write(report_path, mixed_policy_report)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "mixed per-runtime attestation policy",
        )

        wrong_git_source_report = copy.deepcopy(report)
        wrong_git_source_report["results"][0]["buildkit_provenance"]["source_uri"] = (  # type: ignore[index]
            f"https://github.com/example/other.git#{git_sha}"
        )
        _write(report_path, wrong_git_source_report)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "wrong BuildKit Git source URI",
        )

        wrong_recipe_report = copy.deepcopy(report)
        wrong_recipe_report["results"][0]["buildkit_provenance"]["entrypoint"] = "Dockerfile"  # type: ignore[index]
        _write(report_path, wrong_recipe_report)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "wrong BuildKit Dockerfile entrypoint",
        )

        mutable_base_report = copy.deepcopy(report)
        mutable_base_report["results"][0]["buildkit_provenance"]["base_images"][  # type: ignore[index]
            "UV_BASE_IMAGE"
        ] = "ghcr.io/astral-sh/uv:0.11.28"
        _write(report_path, mutable_base_report)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "mutable BuildKit base-image input",
        )

        mixed_base_report = copy.deepcopy(report)
        mixed_base_report["results"][1]["buildkit_provenance"]["base_images"][  # type: ignore[index]
            "PYTHON_BASE_IMAGE"
        ] = "python@sha256:" + "d" * 64
        _write(report_path, mixed_base_report)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "mixed base-image identity across runtimes",
        )

        missing_material_digest_report = copy.deepcopy(report)
        missing_material_digest_report["results"][0]["buildkit_provenance"][  # type: ignore[index]
            "material_sha256_count"
        ] = 0
        _write(report_path, missing_material_digest_report)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "missing immutable material SHA-256 identity",
        )

        bad_sbom_report = copy.deepcopy(report)
        bad_sbom_report["results"][0]["buildkit_sbom"]["package_count"] = -1  # type: ignore[index]
        _write(report_path, bad_sbom_report)
        _expect_failure(
            lambda: _assemble(
                module,
                fragments=fragments,
                git_sha=git_sha,
                version=version,
                run_url=run_url,
                report_path=report_path,
            ),
            "invalid SPDX package count",
        )

    print(
        json.dumps(
            {
                "status": "PASS",
                "runtime_count": 6,
                "negative_drills": [
                    "missing_runtime_blocked",
                    "mutable_tag_blocked",
                    "provenance_sha_swap_blocked",
                    "mixed_build_run_blocked",
                    "missing_attestation_report_blocked",
                    "failed_attestation_report_blocked",
                    "attestation_image_swap_blocked",
                    "stale_attestation_source_digest_blocked",
                    "mixed_runtime_attestation_policy_blocked",
                    "wrong_buildkit_git_source_blocked",
                    "wrong_buildkit_recipe_blocked",
                    "mutable_base_image_blocked",
                    "mixed_runtime_base_image_blocked",
                    "missing_material_sha256_blocked",
                    "invalid_sbom_package_count_blocked",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

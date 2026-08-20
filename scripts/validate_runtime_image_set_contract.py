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


def _attestation_report(images: dict[str, str]) -> dict[str, object]:
    return {
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
                "buildkit_sbom": {
                    "spdx_version": "SPDX-2.3",
                    "package_count": 1,
                },
                "status": "PASS",
            }
            for service in sorted(images)
        ],
    }


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
        report = _attestation_report(images)
        _write(report_path, report)

        clean = module.assemble(
            fragments_dir=fragments,
            git_sha=git_sha,
            version=version,
            build_run_url=run_url,
            attestation_report=report_path,
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
        report_hash = attestation.get("sha256")
        if not isinstance(report_hash, str) or len(report_hash) != 64:
            raise ContractError("clean assembly did not bind attestation report SHA-256")
        if attestation.get("report_file") != "attestation-verification.json":
            raise ContractError("clean assembly did not bind canonical attestation report file")

        missing = fragments / "api.json"
        saved_api = json.loads(missing.read_text(encoding="utf-8"))
        missing.unlink()
        _expect_failure(
            lambda: module.assemble(
                fragments_dir=fragments,
                git_sha=git_sha,
                version=version,
                build_run_url=run_url,
                attestation_report=report_path,
            ),
            "missing runtime fragment",
        )
        _write(missing, saved_api)

        mutable = json.loads(missing.read_text(encoding="utf-8"))
        mutable["image"] = "ghcr.io/example/lumi-api:latest"
        _write(missing, mutable)
        _expect_failure(
            lambda: module.assemble(
                fragments_dir=fragments,
                git_sha=git_sha,
                version=version,
                build_run_url=run_url,
                attestation_report=report_path,
            ),
            "mutable image tag",
        )
        _write(missing, saved_api)

        wrong_sha = json.loads(missing.read_text(encoding="utf-8"))
        wrong_sha["provenance"]["git_sha"] = "b" * 40
        _write(missing, wrong_sha)
        _expect_failure(
            lambda: module.assemble(
                fragments_dir=fragments,
                git_sha=git_sha,
                version=version,
                build_run_url=run_url,
                attestation_report=report_path,
            ),
            "provenance SHA mismatch",
        )
        _write(missing, saved_api)

        wrong_run = json.loads(missing.read_text(encoding="utf-8"))
        wrong_run["build_run_url"] = "https://github.com/example/lumi/actions/runs/999"
        _write(missing, wrong_run)
        _expect_failure(
            lambda: module.assemble(
                fragments_dir=fragments,
                git_sha=git_sha,
                version=version,
                build_run_url=run_url,
                attestation_report=report_path,
            ),
            "mixed build-run provenance",
        )
        _write(missing, saved_api)

        report_path.unlink()
        _expect_failure(
            lambda: module.assemble(
                fragments_dir=fragments,
                git_sha=git_sha,
                version=version,
                build_run_url=run_url,
                attestation_report=report_path,
            ),
            "missing attestation verification report",
        )
        _write(report_path, report)

        failed_report = copy.deepcopy(report)
        failed_report["status"] = "FAIL"
        _write(report_path, failed_report)
        _expect_failure(
            lambda: module.assemble(
                fragments_dir=fragments,
                git_sha=git_sha,
                version=version,
                build_run_url=run_url,
                attestation_report=report_path,
            ),
            "failed attestation verification report",
        )

        image_swap_report = copy.deepcopy(report)
        first = image_swap_report["results"][0]  # type: ignore[index]
        first["image"] = "ghcr.io/example/swapped@sha256:" + "f" * 64  # type: ignore[index]
        _write(report_path, image_swap_report)
        _expect_failure(
            lambda: module.assemble(
                fragments_dir=fragments,
                git_sha=git_sha,
                version=version,
                build_run_url=run_url,
                attestation_report=report_path,
            ),
            "attestation report image mismatch",
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
                    "attestation_image_swap_blocked"
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

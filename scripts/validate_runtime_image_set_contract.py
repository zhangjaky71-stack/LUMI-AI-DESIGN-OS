#!/usr/bin/env python3
from __future__ import annotations

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

        for index, service in enumerate(sorted(module.REQUIRED_RUNTIMES), start=1):
            digest = f"{index:x}" * 64
            image = f"ghcr.io/example/lumi-{service}@sha256:{digest}"
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

        clean = module.assemble(
            fragments_dir=fragments,
            git_sha=git_sha,
            version=version,
            build_run_url=run_url,
        )
        image_set = clean.get("container_image_set")
        if not isinstance(image_set, dict):
            raise ContractError("clean assembly missing container_image_set")
        images = image_set.get("images")
        provenance = image_set.get("provenance")
        if not isinstance(images, dict) or set(images) != set(module.REQUIRED_RUNTIMES):
            raise ContractError("clean assembly did not freeze exactly six images")
        if not isinstance(provenance, dict) or set(provenance) != set(module.REQUIRED_RUNTIMES):
            raise ContractError("clean assembly did not freeze exactly six provenance records")
        if any("@sha256:" not in str(value) for value in images.values()):
            raise ContractError("clean assembly contains a mutable image reference")

        missing = fragments / "api.json"
        saved_api = json.loads(missing.read_text(encoding="utf-8"))
        missing.unlink()
        _expect_failure(
            lambda: module.assemble(
                fragments_dir=fragments,
                git_sha=git_sha,
                version=version,
                build_run_url=run_url,
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
            ),
            "mixed build-run provenance",
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
                    "mixed_build_run_blocked"
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

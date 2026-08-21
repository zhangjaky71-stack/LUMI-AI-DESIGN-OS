#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "staging" / "acceptance" / "manifest-v1.json"
PARITY = ROOT / "staging" / "acceptance" / "environment-parity-v1.json"
TEMPLATE = ROOT / "staging" / "acceptance" / "evidence-template.json"
GATE = ROOT / "scripts" / "staging-acceptance-gate.py"
API_DOCKERFILE = ROOT / "apps" / "api" / "Dockerfile"
API_PYPROJECT = ROOT / "apps" / "api" / "pyproject.toml"
API_CLI = ROOT / "apps" / "api" / "src" / "lumi_api" / "cli.py"
REQUIRED_IMAGES = [
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
]
API_REQUIRED_SOURCES = [
    "apps/api/Dockerfile",
    "apps/api/pyproject.toml",
    "apps/api/alembic.ini",
    "apps/api/alembic/versions/0020_generation_operation_identity.py",
    "apps/api/src/lumi_api/cli.py",
    "apps/api/src/lumi_api/product_app.py",
    "apps/api/src/lumi_api/generations/gateway.py",
    "apps/api/src/lumi_api/generations/service.py",
    "apps/api/src/lumi_api/media_dispatch.py",
]
MODEL_GATEWAY_REQUIRED_SOURCES = [
    "services/model-gateway",
    "services/model-gateway/src/lumi_model_gateway/openai_image_adapter.py",
    "services/asset-storage/src/lumi_asset_storage/s3.py",
    "apps/api/src/lumi_api/model_gateway_runtime.py",
    "apps/api/src/lumi_api/model_gateway_bootstrap.py",
    "apps/api/src/lumi_api/model_gateway_service.py",
    "apps/api/src/lumi_api/model_gateway_cli.py",
    "apps/api/src/lumi_api/model_paid_guard.py",
    "apps/api/src/lumi_api/provider_output_store.py",
    "apps/api/src/lumi_api/idempotency/gateway.py",
    "apps/api/src/lumi_api/costs/model_gateway_adapter.py",
]
WORKER_MEDIA_REQUIRED_SOURCES = [
    "services/image-generation",
    "services/video-generation",
    "services/asset-storage/src/lumi_asset_storage/s3.py",
    "apps/worker-media/Dockerfile",
    "apps/worker-media/pyproject.toml",
    "apps/worker-media/src/lumi_worker_media/app.py",
    "apps/worker-media/src/lumi_worker_media/worker_cli.py",
    "apps/worker-media/src/lumi_worker_media/job_runtime.py",
    "apps/worker-media/src/lumi_worker_media/job_dispatch_runtime.py",
    "apps/worker-media/src/lumi_worker_media/event_runtime.py",
    "apps/worker-media/src/lumi_worker_media/external_wait_runtime.py",
    "apps/worker-media/src/lumi_worker_media/image_gateway_runtime.py",
    "apps/worker-media/src/lumi_worker_media/image_generation_codec.py",
    "apps/worker-media/src/lumi_worker_media/image_generation_repository.py",
    "apps/worker-media/src/lumi_worker_media/image_generation_ports.py",
    "apps/worker-media/src/lumi_worker_media/image_generation_artifacts.py",
    "apps/worker-media/src/lumi_worker_media/image_generation_runtime.py",
    "apps/worker-media/src/lumi_worker_media/video_gateway_runtime.py",
    "apps/worker-media/src/lumi_worker_media/video_generation_codec.py",
    "apps/worker-media/src/lumi_worker_media/video_generation_repository.py",
    "apps/worker-media/src/lumi_worker_media/video_generation_ports.py",
    "apps/worker-media/src/lumi_worker_media/video_generation_artifacts.py",
    "apps/worker-media/src/lumi_worker_media/video_generation_runtime.py",
    "apps/worker-media/src/lumi_worker_media/video_final_probe_runtime.py",
    "apps/worker-media/src/lumi_worker_media/video_validation_runtime.py",
    "apps/worker-media/src/lumi_worker_media/video_sandbox_runtime.py",
    "apps/worker-media/src/lumi_worker_media/video_cost_runtime.py",
]


def load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"{path} must be an object")
    return raw


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_staging_acceptance_gate", GATE)
    if spec is None or spec.loader is None:
        raise SystemExit("unable to import staging acceptance gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"staging acceptance contract invalid: {message}")


def validate_api_image_source_contract() -> None:
    require(API_DOCKERFILE.is_file(), "canonical apps/api/Dockerfile is required")
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
    require("FROM ghcr.io/astral-sh/uv:0.11.28 AS uv" in dockerfile, "api image must pin the canonical uv builder")
    require("FROM python:3.12-slim" in dockerfile, "api image must pin Python 3.12 slim runtime")
    require("COPY . /workspace" in dockerfile, "api image must build from the repository workspace")
    require("uv sync --all-packages --frozen --no-dev" in dockerfile, "api image dependency install must be frozen")
    require("USER 10001:10001" in dockerfile, "api image must run as the canonical non-root uid/gid")
    require('CMD ["lumi-api"]' in dockerfile, "api image must execute the lumi-api console entrypoint")

    pyproject = API_PYPROJECT.read_text(encoding="utf-8")
    require('lumi-api = "lumi_api.cli:main"' in pyproject, "lumi-api console entrypoint must resolve to lumi_api.cli:main")
    cli = API_CLI.read_text(encoding="utf-8")
    require('uvicorn.run("lumi_api.product_app:app"' in cli, "api CLI must start the product control plane")

    for relative in API_REQUIRED_SOURCES:
        require((ROOT / relative).exists(), f"api provenance source {relative} must exist in the accepted source tree")


def validate_worker_media_source_contract() -> None:
    for relative in WORKER_MEDIA_REQUIRED_SOURCES:
        require(
            (ROOT / relative).exists(),
            f"worker-media provenance source {relative} must exist in the accepted source tree",
        )


def clean_image_set(git_sha: str) -> dict[str, Any]:
    images = {
        name: (
            "123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/"
            f"lumi-{name}@sha256:" + chr(97 + index) * 64
        )
        for index, name in enumerate(REQUIRED_IMAGES)
    }
    provenance: dict[str, Any] = {}
    for name in REQUIRED_IMAGES:
        source_paths = [f"apps/{name}"]
        if name == "api":
            source_paths = list(API_REQUIRED_SOURCES)
        elif name == "model-gateway":
            source_paths = list(MODEL_GATEWAY_REQUIRED_SOURCES)
        elif name == "worker-media":
            source_paths = list(WORKER_MEDIA_REQUIRED_SOURCES)
        provenance[name] = {
            "git_sha": git_sha,
            "build_recipe_ref": f"fixture:build:{name}",
            "entrypoint": f"fixture-entrypoint-{name}",
            "sbom_ref": f"fixture:sbom:{name}",
            "provenance_ref": f"fixture:provenance:{name}",
            "source_paths": source_paths,
        }
    return {"images": images, "provenance": provenance}


def clean_evidence(manifest: dict[str, Any], parity: dict[str, Any]) -> dict[str, Any]:
    scenarios = manifest["scenarios"]
    parity_checks = parity["required_checks"]
    git_sha = "c" * 40
    return {
        "schema_version": 1,
        "manifest_id": manifest["manifest_id"],
        "release_candidate": {
            "git_sha": git_sha,
            "version": "0.0.0-rc.contract",
            "environment_id": "staging-contract-fixture",
            "base_url": "https://staging.example.invalid",
            "container_image_set_ref": "fixture:image-set:contract",
            "migration_head": "fixture-migration-head",
        },
        "container_image_set": clean_image_set(git_sha),
        "data_policy": {
            "production_customer_data_used": False,
            "test_data_only": True,
            "staging_secrets_isolated": True,
        },
        "test_accounts": {
            "org_a_owner": "fixture:org-a-owner",
            "org_a_editor": "fixture:org-a-editor",
            "org_a_viewer": "fixture:org-a-viewer",
            "org_b_owner": "fixture:org-b-owner",
            "platform_ops": "fixture:platform-ops",
            "billing_test_org": "fixture:billing-org",
        },
        "provider_modes": {
            "mock_provider": "AVAILABLE",
            "provider_sandbox": "AVAILABLE",
            "production_candidate_quality_sample": "AVAILABLE",
        },
        "environment_parity": {
            item["id"]: {"status": "PASS", "evidence_ref": f"fixture:parity:{item['id']}"}
            for item in parity_checks
        },
        "scenario_results": {
            item["id"]: {
                "status": "PASS",
                "actual": "contract fixture matched expected behavior",
                "evidence_ref": f"fixture:scenario:{item['id']}",
                "owner": "contract-test",
            }
            for item in scenarios
        },
        "open_issues": [],
        "approvals": {
            "engineering": "APPROVED",
            "security": "APPROVED",
            "product": "APPROVED",
            "release_owner": "APPROVED",
        },
    }


def cli_contract_smoke(clean: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory(prefix="lumi-node71-") as temp_dir:
        temp = Path(temp_dir)
        evidence = temp / "evidence.json"
        output = temp / "decision.json"
        markdown = temp / "decision.md"
        evidence.write_text(json.dumps(clean), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(GATE),
                "--evidence",
                str(evidence),
                "--output",
                str(output),
                "--markdown",
                str(markdown),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        require(result.returncode == 0, "workflow CLI contract (--output/--markdown) must execute a clean decision")
        require(output.is_file(), "workflow CLI contract must emit decision JSON")
        require(markdown.is_file(), "workflow CLI contract must emit decision markdown")
        parsed = load_json(output)
        require(parsed.get("passed") is True, "CLI smoke decision must preserve PASS")
        require("Status: **PASS**" in markdown.read_text(encoding="utf-8"), "CLI smoke markdown must render decision status")


def drill_required_sources(
    *,
    gate: ModuleType,
    manifest: dict[str, Any],
    parity: dict[str, Any],
    clean: dict[str, Any],
    service: str,
    required_sources: list[str],
    blocker_fragment: str,
) -> None:
    for required_source in required_sources:
        missing_source = copy.deepcopy(clean)
        source_paths = missing_source["container_image_set"]["provenance"][service]["source_paths"]
        source_paths.remove(required_source)
        decision = gate.evaluate(manifest, parity, missing_source)
        require(decision["passed"] is False, f"{service} image without {required_source} must block")
        require(
            any(blocker_fragment in item for item in decision["blockers"]),
            f"missing {service} source blocker must be explicit",
        )


def main() -> int:
    manifest = load_json(MANIFEST)
    parity = load_json(PARITY)
    template = load_json(TEMPLATE)
    gate = load_gate()
    validate_api_image_source_contract()
    validate_worker_media_source_contract()

    scenarios = manifest.get("scenarios")
    require(isinstance(scenarios, list) and len(scenarios) >= 25, "acceptance manifest must cover the full product surface")
    ids = [item.get("id") for item in scenarios]
    require(len(ids) == len(set(ids)), "scenario IDs must be unique")
    require(all(item.get("priority") in {"P0", "P1"} for item in scenarios), "scenario priorities must be P0/P1")
    require(all(item.get("severity") in {"critical", "high", "medium", "low"} for item in scenarios), "scenario severities invalid")
    require(
        set(getattr(gate, "API_REQUIRED_SOURCE_PATHS", set())) == set(API_REQUIRED_SOURCES),
        "NODE-71 api provenance list drifted from contract drills",
    )
    require(
        set(getattr(gate, "MODEL_GATEWAY_REQUIRED_SOURCE_PATHS", set())) == set(MODEL_GATEWAY_REQUIRED_SOURCES),
        "NODE-71 model-gateway provenance list drifted from contract drills",
    )
    require(
        set(getattr(gate, "WORKER_MEDIA_REQUIRED_SOURCE_PATHS", set())) == set(WORKER_MEDIA_REQUIRED_SOURCES),
        "NODE-71 worker-media provenance list drifted from contract drills",
    )

    pending = gate.evaluate(manifest, parity, template)
    require(pending["passed"] is False, "empty evidence template must never pass")
    require(pending["summary"]["p0_passed"] == 0, "empty template must have zero P0 passes")

    clean = clean_evidence(manifest, parity)
    decision = gate.evaluate(manifest, parity, clean)
    require(decision["passed"] is True, "complete contract fixture must be able to pass")
    require(decision["summary"]["p0_passed"] == decision["summary"]["p0_total"], "all P0 fixtures must pass")
    require(
        decision["container_image_set"]["images"] == clean["container_image_set"]["images"],
        "accepted decision must freeze immutable image digests",
    )
    cli_contract_smoke(clean)

    mutable_image = copy.deepcopy(clean)
    mutable_image["container_image_set"]["images"]["model-gateway"] = "example.invalid/lumi-model-gateway:latest"
    require(gate.evaluate(manifest, parity, mutable_image)["passed"] is False, "mutable model-gateway image must block")

    provenance_sha_swap = copy.deepcopy(clean)
    provenance_sha_swap["container_image_set"]["provenance"]["api"]["git_sha"] = "d" * 40
    require(gate.evaluate(manifest, parity, provenance_sha_swap)["passed"] is False, "image provenance SHA mismatch must block")

    drill_required_sources(
        gate=gate,
        manifest=manifest,
        parity=parity,
        clean=clean,
        service="api",
        required_sources=API_REQUIRED_SOURCES,
        blocker_fragment="api image provenance is missing required generation control-plane sources",
    )
    drill_required_sources(
        gate=gate,
        manifest=manifest,
        parity=parity,
        clean=clean,
        service="model-gateway",
        required_sources=MODEL_GATEWAY_REQUIRED_SOURCES,
        blocker_fragment="model-gateway image provenance is missing required hosted sources",
    )
    drill_required_sources(
        gate=gate,
        manifest=manifest,
        parity=parity,
        clean=clean,
        service="worker-media",
        required_sources=WORKER_MEDIA_REQUIRED_SOURCES,
        blocker_fragment="worker-media image provenance is missing required hosted media sources",
    )

    not_run = copy.deepcopy(clean)
    not_run["scenario_results"]["E2E-01"] = {"status": "NOT_RUN"}
    require(gate.evaluate(manifest, parity, not_run)["passed"] is False, "P0 NOT_RUN must block")

    fake_pass = copy.deepcopy(clean)
    fake_pass["scenario_results"]["E2E-02"] = {"status": "PASS", "actual": "ok", "owner": "contract-test"}
    require(gate.evaluate(manifest, parity, fake_pass)["passed"] is False, "PASS without evidence_ref must block")

    invalid_external = copy.deepcopy(clean)
    invalid_external["scenario_results"]["SEC-01"] = {
        "status": "BLOCKED_EXTERNAL",
        "actual": "dependency missing",
        "evidence_ref": "fixture:ticket:1",
        "owner": "contract-test",
        "external_reason": "fixture dependency",
    }
    invalid_external_decision = gate.evaluate(manifest, parity, invalid_external)
    require(invalid_external_decision["passed"] is False, "non-external scenario cannot use BLOCKED_EXTERNAL")
    require(any("invalid BLOCKED_EXTERNAL" in item for item in invalid_external_decision["blockers"]), "invalid external status must be explicit")

    external_p0 = copy.deepcopy(clean)
    external_p0["scenario_results"]["AI-01"] = {
        "status": "BLOCKED_EXTERNAL",
        "actual": "provider credential unavailable",
        "evidence_ref": "fixture:external:provider",
        "owner": "release-owner",
        "external_reason": "provider account unavailable",
    }
    require(gate.evaluate(manifest, parity, external_p0)["passed"] is False, "P0 BLOCKED_EXTERNAL must still block go-live")

    critical_issue = copy.deepcopy(clean)
    critical_issue["open_issues"] = [{"id": "FIX-1", "severity": "critical", "status": "OPEN", "owner": "contract-test"}]
    require(gate.evaluate(manifest, parity, critical_issue)["passed"] is False, "open critical issue must block")

    parity_fail = copy.deepcopy(clean)
    parity_fail["environment_parity"]["PARITY-IMAGE"] = {"status": "FAIL", "evidence_ref": "fixture:parity:bad"}
    require(gate.evaluate(manifest, parity, parity_fail)["passed"] is False, "environment parity failure must block")

    output = {
        "status": "PASS",
        "manifest_id": manifest["manifest_id"],
        "scenario_count": len(scenarios),
        "p0_count": decision["summary"]["p0_total"],
        "parity_count": decision["summary"]["parity_total"],
        "clean_fixture_decision": decision["decision_id"],
        "drills": {
            "empty_template_blocked": True,
            "mutable_image_blocked": True,
            "image_provenance_sha_swap_blocked": True,
            "api_all_required_sources_drilled": True,
            "api_build_recipe_source_required": True,
            "api_console_entrypoint_source_required": True,
            "api_product_app_source_required": True,
            "api_generation_gateway_source_required": True,
            "api_generation_service_source_required": True,
            "api_media_dispatch_source_required": True,
            "api_generation_operation_migration_source_required": True,
            "api_frozen_non_root_image_contract": True,
            "model_gateway_all_required_sources_drilled": True,
            "model_gateway_media_adapter_source_required": True,
            "model_gateway_provider_output_store_source_required": True,
            "model_gateway_asset_storage_source_required": True,
            "worker_media_all_required_media_sources_drilled": True,
            "worker_media_build_recipe_source_required": True,
            "worker_media_entrypoint_source_required": True,
            "worker_media_image_generation_domain_source_required": True,
            "worker_media_image_gateway_source_required": True,
            "worker_media_video_generation_domain_source_required": True,
            "worker_media_video_gateway_source_required": True,
            "worker_media_video_repository_source_required": True,
            "worker_media_video_ports_source_required": True,
            "worker_media_video_artifact_source_required": True,
            "worker_media_video_sandbox_source_required": True,
            "worker_media_video_final_probe_source_required": True,
            "worker_media_video_validation_source_required": True,
            "worker_media_video_cost_source_required": True,
            "worker_media_external_wait_source_required": True,
            "worker_media_job_dispatch_source_required": True,
            "workflow_cli_output_markdown_smoke": True,
            "p0_not_run_blocked": True,
            "unevidenced_pass_blocked": True,
            "invalid_external_blocked": True,
            "p0_external_still_blocks": True,
            "critical_issue_blocked": True,
            "parity_failure_blocked": True,
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

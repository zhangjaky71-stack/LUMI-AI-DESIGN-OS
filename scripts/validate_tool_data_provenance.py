#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_API_SOURCES = frozenset(
    {
        "apps/api/src/lumi_api/product_app.py",
        "apps/api/src/lumi_api/tool_data_control.py",
        "apps/api/src/lumi_api/persistence/models/project.py",
        "apps/api/src/lumi_api/persistence/models/workflow.py",
        "apps/api/src/lumi_api/persistence/models/asset.py",
        "apps/api/src/lumi_api/persistence/models/design.py",
    }
)
REQUIRED_TOOL_GATEWAY_SOURCES = frozenset(
    {
        "services/tool-gateway/src/lumi_tool_gateway/service.py",
        "services/tool-gateway/src/lumi_tool_gateway/data_control.py",
        "services/tool-gateway/src/lumi_tool_gateway/catalog.py",
        "services/tool-gateway/src/lumi_tool_gateway/http_transport.py",
    }
)
CORE_FILES = (
    ROOT / "infra/iac/environments/staging/core/main.tf",
    ROOT / "infra/iac/environments/production/core/main.tf",
)
APP_FILES = (
    ROOT / "infra/iac/environments/staging/app/main.tf",
    ROOT / "infra/iac/environments/production/app/main.tf",
)
PUBLIC_DENY = ROOT / "infra/iac/modules/platform-app/internal-path-deny.tf"


class ToolDataProvenanceError(RuntimeError):
    pass


def _source_paths(payload: dict[str, Any], service: str) -> set[str]:
    image_set = payload.get("container_image_set")
    if not isinstance(image_set, dict):
        raise ToolDataProvenanceError("container_image_set is missing")
    provenance = image_set.get("provenance")
    if not isinstance(provenance, dict):
        raise ToolDataProvenanceError("container_image_set.provenance is missing")
    service_provenance = provenance.get(service)
    if not isinstance(service_provenance, dict):
        raise ToolDataProvenanceError(f"{service} image provenance is missing")
    source_paths = service_provenance.get("source_paths")
    if not isinstance(source_paths, list) or not all(
        isinstance(item, str) and item for item in source_paths
    ):
        raise ToolDataProvenanceError(
            f"{service} image provenance source_paths is invalid"
        )
    return set(source_paths)


def validate_evidence(payload: dict[str, Any]) -> None:
    api_sources = _source_paths(payload, "api")
    missing_api = sorted(REQUIRED_API_SOURCES - api_sources)
    if missing_api:
        raise ToolDataProvenanceError(
            "api image provenance is missing canonical Tool Data sources: "
            + ", ".join(missing_api)
        )
    tool_sources = _source_paths(payload, "tool-gateway")
    missing_tool = sorted(REQUIRED_TOOL_GATEWAY_SOURCES - tool_sources)
    if missing_tool:
        raise ToolDataProvenanceError(
            "tool-gateway image provenance is missing Tool Data adapter sources: "
            + ", ".join(missing_tool)
        )


def validate_source_chain() -> None:
    for relative in (*REQUIRED_API_SOURCES, *REQUIRED_TOOL_GATEWAY_SOURCES):
        if not (ROOT / relative).is_file():
            raise ToolDataProvenanceError(
                f"required Tool Data source is missing: {relative}"
            )

    api_control = (ROOT / "apps/api/src/lumi_api/tool_data_control.py").read_text(
        encoding="utf-8"
    )
    for fragment in (
        'frozenset({"tool-gateway"})',
        '"project.summary"',
        "Task.organization_id == organization_id",
        "Task.agent_run_id == agent_run_id",
        "Project.id == project_id",
        "Asset.project_id == project_id",
        "Artifact.project_id == project_id",
        '@router.post("/asset/read")',
        '@router.post("/artifact/query")',
        '@router.post("/media/inspect")',
        "hmac.compare_digest",
    ):
        if fragment not in api_control:
            raise ToolDataProvenanceError(
                f"canonical Tool Data control is missing boundary: {fragment}"
            )
    for forbidden in ("item.bucket", "item.object_key", "generate_presigned_url"):
        if forbidden in api_control:
            raise ToolDataProvenanceError(
                f"canonical Tool Data read path leaks storage location: {forbidden}"
            )

    product_app = (ROOT / "apps/api/src/lumi_api/product_app.py").read_text(
        encoding="utf-8"
    )
    for fragment in (
        "create_tool_data_control_router",
        "build_tool_data_control_runtime(session_factory)",
        "tool_data_control_enabled",
        "tool data control plane unavailable",
    ):
        if fragment not in product_app:
            raise ToolDataProvenanceError(
                f"Product API is missing Tool Data control binding: {fragment}"
            )

    gateway_client = (
        ROOT / "services/tool-gateway/src/lumi_tool_gateway/data_control.py"
    ).read_text(encoding="utf-8")
    for fragment in (
        "class HttpToolDataClient",
        'os.getenv("LUMI_TOOL_DATA_URL"',
        'os.getenv("LUMI_TOOL_DATA_AUTH_SECRET"',
        'service="tool-gateway"',
        "class ProjectQueryAdapter",
        "class AssetReadAdapter",
        "class ArtifactQueryAdapter",
        "class MediaInspectAdapter",
        'resource_refs=(f"asset://',
        'resource_refs=(f"artifact://',
    ):
        if fragment not in gateway_client:
            raise ToolDataProvenanceError(
                f"Tool Gateway data client is missing boundary: {fragment}"
            )
    if "project_id =" in gateway_client or 'arguments.get("project_id")' in gateway_client:
        raise ToolDataProvenanceError(
            "Tool Gateway project query must derive project scope from canonical Task"
        )

    catalog = (ROOT / "services/tool-gateway/src/lumi_tool_gateway/catalog.py").read_text(
        encoding="utf-8"
    )
    for fragment in (
        'name="project.query"',
        '"enum": ["project.summary"]',
        'name="asset.read"',
        'name="artifact.query"',
        'name="media.inspect"',
        '"additionalProperties": False',
    ):
        if fragment not in catalog:
            raise ToolDataProvenanceError(
                f"Tool Gateway data catalog is missing boundary: {fragment}"
            )

    hosted_service = (
        ROOT / "services/tool-gateway/src/lumi_tool_gateway/service.py"
    ).read_text(encoding="utf-8")
    for fragment in (
        "HttpToolDataClient.from_env()",
        '"project.query@1.0.0": ProjectQueryAdapter(data_client)',
        '"asset.read@1.0.0": AssetReadAdapter(data_client)',
        '"artifact.query@1.0.0": ArtifactQueryAdapter(data_client)',
        '"media.inspect@1.0.0": MediaInspectAdapter(data_client)',
        "ToolDataControlUnavailableError",
    ):
        if fragment not in hosted_service:
            raise ToolDataProvenanceError(
                f"Hosted Tool Gateway is missing Tool Data binding: {fragment}"
            )

    for path in CORE_FILES:
        source = path.read_text(encoding="utf-8")
        if '"internal/tool-data"' not in source:
            raise ToolDataProvenanceError(
                f"{path.relative_to(ROOT)} missing internal/tool-data"
            )

    for path in APP_FILES:
        source = path.read_text(encoding="utf-8")
        for fragment in (
            "LUMI_TOOL_DATA_URL",
            "api.${local.environment}.lumi.internal:8000",
            "LUMI_TOOL_DATA_AUTH_SECRET",
            'local.secret_arns["internal/tool-data"]',
        ):
            if fragment not in source:
                raise ToolDataProvenanceError(
                    f"{path.relative_to(ROOT)} missing Tool Data wiring: {fragment}"
                )
        if source.count("LUMI_TOOL_DATA_AUTH_SECRET") != 2:
            relative = path.relative_to(ROOT)
            raise ToolDataProvenanceError(
                f"{relative} must inject Tool Data secret only into API and Tool Gateway"
            )
        agent_block = _terraform_service_block(source, "agent-runtime")
        if "LUMI_TOOL_DATA" in agent_block or "internal/tool-data" in agent_block:
            raise ToolDataProvenanceError(
                f"{path.relative_to(ROOT)} leaks Tool Data control to Agent Runtime"
            )

    deny = PUBLIC_DENY.read_text(encoding="utf-8")
    for fragment in (
        "priority     = 1",
        'status_code  = "404"',
        'values = ["/internal", "/internal/*"]',
    ):
        if fragment not in deny:
            raise ToolDataProvenanceError(
                f"public ALB internal-path deny missing boundary: {fragment}"
            )


def _terraform_service_block(source: str, service_name: str) -> str:
    marker = f"    {service_name} = {{"
    start = source.find(marker)
    if start < 0:
        raise ToolDataProvenanceError(
            f"Terraform service block is missing: {service_name}"
        )
    brace = source.find("{", start)
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise ToolDataProvenanceError(
        f"Terraform service block is unterminated: {service_name}"
    )


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolDataProvenanceError(f"unable to read evidence JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ToolDataProvenanceError("evidence must be a JSON object")
    return payload


def self_test() -> None:
    validate_source_chain()
    clean = {
        "container_image_set": {
            "provenance": {
                "api": {"source_paths": sorted(REQUIRED_API_SOURCES)},
                "tool-gateway": {
                    "source_paths": sorted(REQUIRED_TOOL_GATEWAY_SOURCES)
                },
            }
        }
    }
    validate_evidence(clean)
    broken = json.loads(json.dumps(clean))
    broken["container_image_set"]["provenance"]["api"]["source_paths"].remove(
        "apps/api/src/lumi_api/tool_data_control.py"
    )
    try:
        validate_evidence(broken)
    except ToolDataProvenanceError:
        pass
    else:
        raise ToolDataProvenanceError(
            "self-test accepted missing canonical Tool Data API source"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.evidence is not None:
        validate_source_chain()
        validate_evidence(_load(args.evidence))
    if not args.self_test and args.evidence is None:
        parser.error("one of --self-test or --evidence is required")
    print("Tool Gateway durable Tool Data provenance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

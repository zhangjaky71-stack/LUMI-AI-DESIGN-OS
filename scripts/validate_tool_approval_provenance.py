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
        "apps/api/src/lumi_api/tool_approval_control.py",
        "apps/api/src/lumi_api/persistence/models/workflow.py",
        "apps/api/alembic/versions/0021_tool_approval_scope.py",
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


class ToolApprovalProvenanceError(RuntimeError):
    pass


def validate_evidence(payload: dict[str, Any]) -> None:
    image_set = payload.get("container_image_set")
    if not isinstance(image_set, dict):
        raise ToolApprovalProvenanceError("container_image_set is missing")
    provenance = image_set.get("provenance")
    if not isinstance(provenance, dict):
        raise ToolApprovalProvenanceError("container_image_set.provenance is missing")
    api = provenance.get("api")
    if not isinstance(api, dict):
        raise ToolApprovalProvenanceError("api image provenance is missing")
    source_paths = api.get("source_paths")
    if not isinstance(source_paths, list) or not all(
        isinstance(item, str) and item for item in source_paths
    ):
        raise ToolApprovalProvenanceError("api image provenance source_paths is invalid")
    missing = sorted(REQUIRED_API_SOURCES - set(source_paths))
    if missing:
        raise ToolApprovalProvenanceError(
            "api image provenance is missing canonical Tool Gateway approval sources: "
            + ", ".join(missing)
        )


def validate_source_chain() -> None:
    for relative in REQUIRED_API_SOURCES:
        if not (ROOT / relative).is_file():
            raise ToolApprovalProvenanceError(
                f"required Tool Gateway approval source is missing: {relative}"
            )

    migration = (
        ROOT / "apps/api/alembic/versions/0021_tool_approval_scope.py"
    ).read_text(encoding="utf-8")
    for fragment in (
        'down_revision = "0020_generation_operation_identity"',
        "tool_request_hash char(64)",
        "uq_approvals_tool_request",
        "ck_approvals_tool_scope_complete",
    ):
        if fragment not in migration:
            raise ToolApprovalProvenanceError(
                f"canonical tool approval migration is missing boundary: {fragment}"
            )

    api_control = (ROOT / "apps/api/src/lumi_api/tool_approval_control.py").read_text(
        encoding="utf-8"
    )
    for fragment in (
        'frozenset({"tool-gateway"})',
        "class ToolApprovalStore",
        "Approval.tool_request_hash == scope.request_hash",
        '"artifact.approve" not in context.permissions',
        "hmac.compare_digest",
        "with_for_update()",
    ):
        if fragment not in api_control:
            raise ToolApprovalProvenanceError(
                f"canonical Tool Approval control is missing boundary: {fragment}"
            )

    gateway_resolver = (
        ROOT / "services/tool-gateway/src/lumi_tool_gateway/approval_control.py"
    ).read_text(encoding="utf-8")
    for fragment in (
        "class HttpApprovalResolver",
        'service="tool-gateway"',
        'os.getenv("LUMI_TOOL_APPROVAL_URL"',
        'os.getenv("LUMI_TOOL_APPROVAL_AUTH_SECRET"',
        '"approval_id": request.approval_token',
    ):
        if fragment not in gateway_resolver:
            raise ToolApprovalProvenanceError(
                f"Tool Gateway approval resolver is missing boundary: {fragment}"
            )

    hosted_service = (
        ROOT / "services/tool-gateway/src/lumi_tool_gateway/service.py"
    ).read_text(encoding="utf-8")
    for fragment in (
        "HttpApprovalResolver.from_env()",
        "approval_resolver=approval_resolver",
        '"approval-resolver"',
    ):
        if fragment not in hosted_service:
            raise ToolApprovalProvenanceError(
                f"Hosted Tool Gateway is missing approval binding: {fragment}"
            )

    for path in CORE_FILES:
        source = path.read_text(encoding="utf-8")
        if '"internal/tool-approval"' not in source:
            raise ToolApprovalProvenanceError(
                f"{path.relative_to(ROOT)} missing internal/tool-approval"
            )

    for path in APP_FILES:
        source = path.read_text(encoding="utf-8")
        for fragment in (
            "LUMI_TOOL_APPROVAL_URL",
            "api.${local.environment}.lumi.internal:8000",
            "LUMI_TOOL_APPROVAL_AUTH_SECRET",
            'local.secret_arns["internal/tool-approval"]',
        ):
            if fragment not in source:
                raise ToolApprovalProvenanceError(
                    f"{path.relative_to(ROOT)} missing approval wiring: {fragment}"
                )
        if source.count("LUMI_TOOL_APPROVAL_AUTH_SECRET") != 2:
            raise ToolApprovalProvenanceError(
                f"{path.relative_to(ROOT)} must inject approval secret only into API and Tool Gateway"
            )

    deny = PUBLIC_DENY.read_text(encoding="utf-8")
    for fragment in (
        "priority     = 1",
        'status_code  = "404"',
        'values = ["/internal", "/internal/*"]',
    ):
        if fragment not in deny:
            raise ToolApprovalProvenanceError(
                f"public ALB internal-path deny missing boundary: {fragment}"
            )


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolApprovalProvenanceError(f"unable to read evidence JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ToolApprovalProvenanceError("evidence must be a JSON object")
    return payload


def self_test() -> None:
    validate_source_chain()
    clean = {
        "container_image_set": {
            "provenance": {"api": {"source_paths": sorted(REQUIRED_API_SOURCES)}}
        }
    }
    validate_evidence(clean)
    broken = json.loads(json.dumps(clean))
    broken["container_image_set"]["provenance"]["api"]["source_paths"].remove(
        "apps/api/src/lumi_api/tool_approval_control.py"
    )
    try:
        validate_evidence(broken)
    except ToolApprovalProvenanceError:
        pass
    else:
        raise ToolApprovalProvenanceError("self-test accepted missing canonical approval source")


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
    print("Tool Gateway durable approval provenance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

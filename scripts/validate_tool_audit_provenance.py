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
        "apps/api/src/lumi_api/tool_audit_control.py",
        "apps/api/src/lumi_api/persistence/models/platform.py",
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


class ToolAuditProvenanceError(RuntimeError):
    pass


def validate_evidence(payload: dict[str, Any]) -> None:
    image_set = payload.get("container_image_set")
    if not isinstance(image_set, dict):
        raise ToolAuditProvenanceError("container_image_set is missing")
    provenance = image_set.get("provenance")
    if not isinstance(provenance, dict):
        raise ToolAuditProvenanceError("container_image_set.provenance is missing")
    api = provenance.get("api")
    if not isinstance(api, dict):
        raise ToolAuditProvenanceError("api image provenance is missing")
    source_paths = api.get("source_paths")
    if not isinstance(source_paths, list) or not all(
        isinstance(item, str) and item for item in source_paths
    ):
        raise ToolAuditProvenanceError("api image provenance source_paths is invalid")
    missing = sorted(REQUIRED_API_SOURCES - set(source_paths))
    if missing:
        raise ToolAuditProvenanceError(
            "api image provenance is missing canonical Tool Gateway audit sources: "
            + ", ".join(missing)
        )


def validate_source_chain() -> None:
    for relative in REQUIRED_API_SOURCES:
        if not (ROOT / relative).is_file():
            raise ToolAuditProvenanceError(f"required API audit source is missing: {relative}")

    api_control = (ROOT / "apps/api/src/lumi_api/tool_audit_control.py").read_text(
        encoding="utf-8"
    )
    for fragment in (
        'frozenset({"tool-gateway"})',
        "insert(AuditEvent)",
        ".on_conflict_do_nothing",
        'existing.get("event_hash")',
        "hmac.compare_digest",
        "_require_redacted(arguments)",
    ):
        if fragment not in api_control:
            raise ToolAuditProvenanceError(
                f"canonical Tool Audit control is missing boundary: {fragment}"
            )

    tool_sink = (
        ROOT / "services/tool-gateway/src/lumi_tool_gateway/audit_control.py"
    ).read_text(encoding="utf-8")
    for fragment in (
        "class HttpAuditSink",
        'service="tool-gateway"',
        "await asyncio.to_thread",
        'os.getenv("LUMI_TOOL_AUDIT_URL"',
        'os.getenv("LUMI_TOOL_AUDIT_AUTH_SECRET"',
    ):
        if fragment not in tool_sink:
            raise ToolAuditProvenanceError(
                f"Tool Gateway durable audit sink is missing boundary: {fragment}"
            )

    for path in CORE_FILES:
        source = path.read_text(encoding="utf-8")
        if '"internal/tool-audit"' not in source:
            raise ToolAuditProvenanceError(f"{path.relative_to(ROOT)} missing internal/tool-audit")

    for path in APP_FILES:
        source = path.read_text(encoding="utf-8")
        for fragment in (
            "LUMI_TOOL_AUDIT_URL",
            "api.${local.environment}.lumi.internal:8000",
            "LUMI_TOOL_AUDIT_AUTH_SECRET",
            'local.secret_arns["internal/tool-audit"]',
        ):
            if fragment not in source:
                raise ToolAuditProvenanceError(
                    f"{path.relative_to(ROOT)} missing audit wiring: {fragment}"
                )
        if source.count("LUMI_TOOL_AUDIT_AUTH_SECRET") < 2:
            raise ToolAuditProvenanceError(
                f"{path.relative_to(ROOT)} must inject audit secret into API and Tool Gateway"
            )

    deny = PUBLIC_DENY.read_text(encoding="utf-8")
    for fragment in (
        "priority     = 1",
        'status_code  = "404"',
        'values = ["/internal", "/internal/*"]',
    ):
        if fragment not in deny:
            raise ToolAuditProvenanceError(
                f"public ALB internal-path deny missing boundary: {fragment}"
            )


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolAuditProvenanceError(f"unable to read evidence JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ToolAuditProvenanceError("evidence must be a JSON object")
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
        "apps/api/src/lumi_api/tool_audit_control.py"
    )
    try:
        validate_evidence(broken)
    except ToolAuditProvenanceError:
        pass
    else:
        raise ToolAuditProvenanceError("self-test accepted missing canonical audit source")


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
    print("Tool Gateway durable audit provenance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

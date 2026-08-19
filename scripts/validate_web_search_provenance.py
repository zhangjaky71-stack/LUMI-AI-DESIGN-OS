#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TOOL_GATEWAY_SOURCES = frozenset(
    {
        "services/tool-gateway/Dockerfile",
        "services/tool-gateway/src/lumi_tool_gateway/service.py",
        "services/tool-gateway/src/lumi_tool_gateway/search_backend.py",
        "services/tool-gateway/src/lumi_tool_gateway/native.py",
        "services/tool-gateway/src/lumi_tool_gateway/catalog.py",
        "services/tool-gateway/src/lumi_tool_gateway/errors.py",
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
NETWORK_MODULE = ROOT / "infra/iac/modules/network/main.tf"
COMPUTE_MODULE = ROOT / "infra/iac/modules/compute/main.tf"


class WebSearchProvenanceError(RuntimeError):
    pass


def _tool_gateway_sources(payload: dict[str, Any]) -> set[str]:
    image_set = payload.get("container_image_set")
    if not isinstance(image_set, dict):
        raise WebSearchProvenanceError("container_image_set is missing")
    provenance = image_set.get("provenance")
    if not isinstance(provenance, dict):
        raise WebSearchProvenanceError("container_image_set.provenance is missing")
    tool_gateway = provenance.get("tool-gateway")
    if not isinstance(tool_gateway, dict):
        raise WebSearchProvenanceError("tool-gateway image provenance is missing")
    source_paths = tool_gateway.get("source_paths")
    if not isinstance(source_paths, list) or not all(
        isinstance(item, str) and item for item in source_paths
    ):
        raise WebSearchProvenanceError(
            "tool-gateway image provenance source_paths is invalid"
        )
    return set(source_paths)


def validate_evidence(payload: dict[str, Any]) -> None:
    source_paths = _tool_gateway_sources(payload)
    missing = sorted(REQUIRED_TOOL_GATEWAY_SOURCES - source_paths)
    if missing:
        raise WebSearchProvenanceError(
            "tool-gateway image provenance is missing hosted web-search sources: "
            + ", ".join(missing)
        )


def validate_source_chain() -> None:
    for relative in REQUIRED_TOOL_GATEWAY_SOURCES:
        if not (ROOT / relative).is_file():
            raise WebSearchProvenanceError(
                f"required hosted web-search source is missing: {relative}"
            )

    dockerfile = (ROOT / "services/tool-gateway/Dockerfile").read_text(encoding="utf-8")
    for fragment in (
        "COPY . /workspace",
        "uv sync --all-packages --frozen --no-dev",
        "USER 10001:10001",
    ):
        if fragment not in dockerfile:
            raise WebSearchProvenanceError(
                f"Tool Gateway image closure is missing boundary: {fragment}"
            )

    backend = (
        ROOT / "services/tool-gateway/src/lumi_tool_gateway/search_backend.py"
    ).read_text(encoding="utf-8")
    for fragment in (
        '"https://api.search.brave.com/res/v1/web/search"',
        '"X-Subscription-Token": self._api_key',
        'os.getenv("LUMI_BRAVE_SEARCH_API_KEY"',
        "class _NoRedirectHandler",
        "urllib.request.build_opener(_NoRedirectHandler())",
        '"Cache-Control": "no-cache"',
        "_MAX_QUERY_CHARS = 400",
        "_MAX_QUERY_WORDS = 50",
        "_MAX_RESULTS = 20",
        "_MAX_RESPONSE_BYTES = 2 * 1024 * 1024",
        'parsed.scheme.lower() in {"http", "https"}',
        "parsed.username is None",
        "parsed.password is None",
    ):
        if fragment not in backend:
            raise WebSearchProvenanceError(
                f"hosted web-search backend is missing boundary: {fragment}"
            )
    for forbidden in (
        "LUMI_BRAVE_SEARCH_URL",
        "LUMI_WEB_SEARCH_URL",
        "HTTPRedirectHandler()",
    ):
        if forbidden in backend:
            raise WebSearchProvenanceError(
                f"hosted web-search backend contains forbidden boundary: {forbidden}"
            )

    service = (
        ROOT / "services/tool-gateway/src/lumi_tool_gateway/service.py"
    ).read_text(encoding="utf-8")
    for fragment in (
        "BraveSearchBackend.from_env()",
        '"web.search@1.0.0": WebSearchAdapter(',
        "ToolWebSearchUnavailableError",
    ):
        if fragment not in service:
            raise WebSearchProvenanceError(
                f"Hosted Tool Gateway is missing web-search binding: {fragment}"
            )

    native = (
        ROOT / "services/tool-gateway/src/lumi_tool_gateway/native.py"
    ).read_text(encoding="utf-8")
    for fragment in (
        "class WebSearchAdapter",
        '"title": str(row.get("title", ""))[:500]',
        '"url": str(row.get("url", ""))[:4096]',
        '"snippet": str(row.get("snippet", ""))[:4000]',
    ):
        if fragment not in native:
            raise WebSearchProvenanceError(
                f"WebSearchAdapter normalization is missing boundary: {fragment}"
            )

    catalog = (ROOT / "services/tool-gateway/src/lumi_tool_gateway/catalog.py").read_text(
        encoding="utf-8"
    )
    for fragment in (
        'name="web.search"',
        '"query": {"type": "string", "minLength": 1, "maxLength": 400}',
        '"limit": {"type": "integer", "minimum": 1, "maximum": 20}',
        'permissions=frozenset({"tool.web.search"})',
    ):
        if fragment not in catalog:
            raise WebSearchProvenanceError(
                f"web-search catalog is missing boundary: {fragment}"
            )

    for path in CORE_FILES:
        source = path.read_text(encoding="utf-8")
        if source.count('"providers/search"') != 1:
            raise WebSearchProvenanceError(
                f"{path.relative_to(ROOT)} must provision exactly one providers/search secret"
            )

    for path in APP_FILES:
        source = path.read_text(encoding="utf-8")
        if source.count("LUMI_BRAVE_SEARCH_API_KEY") != 1:
            raise WebSearchProvenanceError(
                f"{path.relative_to(ROOT)} must inject Brave key only into Tool Gateway"
            )
        if source.count('local.secret_arns["providers/search"]') != 1:
            raise WebSearchProvenanceError(
                f"{path.relative_to(ROOT)} must bind exactly one providers/search secret"
            )
        agent_block = _terraform_service_block(source, "agent-runtime")
        if "LUMI_BRAVE_SEARCH_API_KEY" in agent_block or "providers/search" in agent_block:
            raise WebSearchProvenanceError(
                f"{path.relative_to(ROOT)} leaks search provider credentials to Agent Runtime"
            )

    network = NETWORK_MODULE.read_text(encoding="utf-8")
    for fragment in (
        'resource "aws_security_group" "app_internet_egress"',
        'cidr_blocks = ["0.0.0.0/0"]',
        'resource "aws_security_group" "sandbox_egress"',
        'EgressPolicy     = "deny-public-except-s3"',
    ):
        if fragment not in network:
            raise WebSearchProvenanceError(
                f"network module is missing hosted search egress boundary: {fragment}"
            )

    compute = COMPUTE_MODULE.read_text(encoding="utf-8")
    for fragment in (
        'name == "sandbox-runtime"',
        "var.app_internet_egress_security_group_id",
        "var.sandbox_egress_security_group_id",
    ):
        if fragment not in compute:
            raise WebSearchProvenanceError(
                f"compute module is missing runtime egress selection: {fragment}"
            )


def _terraform_service_block(source: str, service_name: str) -> str:
    marker = f"    {service_name} = {{"
    start = source.find(marker)
    if start < 0:
        raise WebSearchProvenanceError(
            f"Terraform service block is missing: {service_name}"
        )
    brace = source.find("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise WebSearchProvenanceError(
        f"Terraform service block is unterminated: {service_name}"
    )


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WebSearchProvenanceError(f"unable to read evidence JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise WebSearchProvenanceError("evidence must be a JSON object")
    return payload


def self_test() -> None:
    validate_source_chain()
    clean = {
        "container_image_set": {
            "provenance": {
                "tool-gateway": {
                    "source_paths": sorted(REQUIRED_TOOL_GATEWAY_SOURCES)
                }
            }
        }
    }
    validate_evidence(clean)
    broken = json.loads(json.dumps(clean))
    broken["container_image_set"]["provenance"]["tool-gateway"]["source_paths"].remove(
        "services/tool-gateway/src/lumi_tool_gateway/search_backend.py"
    )
    try:
        validate_evidence(broken)
    except WebSearchProvenanceError:
        pass
    else:
        raise WebSearchProvenanceError(
            "self-test accepted missing hosted web-search source"
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
    print("Tool Gateway hosted web-search provenance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

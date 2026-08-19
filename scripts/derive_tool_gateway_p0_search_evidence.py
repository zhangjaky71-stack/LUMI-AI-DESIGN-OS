#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

_DEFAULT_PROBE = "reports/staging-acceptance/runtime/tool-gateway-p0-probe.json"
_DEFAULT_STAGING = "reports/staging-acceptance/runtime/staging-evidence.json"
_DEFAULT_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-search-evidence.json"
_IMAGE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
_REQUIRED_SOURCES = frozenset(
    {
        "services/tool-gateway/src/lumi_tool_gateway/search_backend.py",
        "services/tool-gateway/src/lumi_tool_gateway/native.py",
        "services/tool-gateway/src/lumi_tool_gateway/service.py",
        "services/tool-gateway/src/lumi_tool_gateway/catalog.py",
        "services/tool-gateway/src/lumi_tool_gateway/errors.py",
    }
)


class SearchEvidenceError(RuntimeError):
    pass


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SearchEvidenceError(f"unable to read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise SearchEvidenceError(f"{label} must be a JSON object")
    return payload


def _successful_status(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {"success", "succeeded", "ok", "completed"}


def _search_call(probe: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if probe.get("caller_service") != "agent-runtime":
        raise SearchEvidenceError("probe caller_service must be agent-runtime")
    calls = probe.get("calls")
    if not isinstance(calls, dict):
        raise SearchEvidenceError("probe calls are missing")
    entry = calls.get("web.search")
    if not isinstance(entry, dict):
        raise SearchEvidenceError("probe web.search call is missing")
    request = entry.get("request")
    result = entry.get("result")
    if not isinstance(request, dict) or not isinstance(result, dict):
        raise SearchEvidenceError("probe web.search request/result is missing")
    if not _successful_status(result.get("status")):
        raise SearchEvidenceError("probe web.search did not succeed")
    if result.get("resolved_name") not in {None, "web.search"}:
        raise SearchEvidenceError("probe web.search resolved to an unexpected tool")
    if result.get("resolved_version") != "1.0.0":
        raise SearchEvidenceError("probe web.search resolved_version must be 1.0.0")
    data = result.get("data")
    if not isinstance(data, dict):
        raise SearchEvidenceError("probe web.search data is missing")
    rows = data.get("results")
    if not isinstance(rows, list) or not rows:
        raise SearchEvidenceError("probe web.search returned no live results")
    return request, result


def _tool_gateway_provenance(staging: dict[str, Any]) -> tuple[str, set[str]]:
    image_set = staging.get("container_image_set")
    if not isinstance(image_set, dict):
        raise SearchEvidenceError("staging container_image_set is missing")
    images = image_set.get("images")
    provenance = image_set.get("provenance")
    if not isinstance(images, dict) or not isinstance(provenance, dict):
        raise SearchEvidenceError("staging Tool Gateway image/provenance is missing")
    image = images.get("tool-gateway")
    if not isinstance(image, str) or not _IMAGE.fullmatch(image):
        raise SearchEvidenceError("staging Tool Gateway image must be digest-pinned")
    tool = provenance.get("tool-gateway")
    if not isinstance(tool, dict):
        raise SearchEvidenceError("staging Tool Gateway provenance is missing")
    paths = tool.get("source_paths")
    if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
        raise SearchEvidenceError("staging Tool Gateway source_paths are invalid")
    sources = set(paths)
    missing = sorted(_REQUIRED_SOURCES - sources)
    if missing:
        raise SearchEvidenceError(
            "staging Tool Gateway provenance is missing Brave sources: " + ", ".join(missing)
        )
    return image, sources


def _secret_markers_absent(probe: dict[str, Any]) -> bool:
    serialized = json.dumps(probe, sort_keys=True)
    forbidden = (
        "X-Subscription-Token",
        "x-subscription-token",
        "LUMI_BRAVE_SEARCH_API_KEY",
        "providers/search",
    )
    return not any(marker in serialized for marker in forbidden)


def derive(probe: dict[str, Any], staging: dict[str, Any]) -> dict[str, Any]:
    request, result = _search_call(probe)
    image, _ = _tool_gateway_provenance(staging)
    data = result["data"]
    rows = data["results"]
    if not _secret_markers_absent(probe):
        raise SearchEvidenceError("probe output contains search credential markers")
    trace_id = request.get("trace_id")
    tool_call_id = request.get("tool_call_id")
    if not isinstance(trace_id, str) or not trace_id:
        raise SearchEvidenceError("probe web.search trace_id is missing")
    if not isinstance(tool_call_id, str) or not tool_call_id:
        raise SearchEvidenceError("probe web.search tool_call_id is missing")
    return {
        "schema_version": 1,
        "provider": "brave",
        "provider_host": "api.search.brave.com",
        "live_request_observed": True,
        "provider_http_status": 200,
        "result_count": len(rows),
        "redirect_followed": False,
        "credential_material_present": False,
        "tool_call_id": tool_call_id,
        "trace_id": trace_id,
        "tool_gateway_image": image,
        "observation_basis": (
            "successful Agent Runtime web.search call on the digest-pinned RC plus "
            "fixed Brave Search backend provenance; backend returns only after HTTP 200 "
            "and its transport forbids redirects"
        ),
        "direct_packet_capture": False,
    }


def main() -> int:
    probe_path = Path(os.getenv("LUMI_PROBE_INPUT", _DEFAULT_PROBE))
    staging_path = Path(os.getenv("LUMI_STAGING_EVIDENCE_INPUT", _DEFAULT_STAGING))
    output_path = Path(os.getenv("LUMI_SEARCH_EVIDENCE_OUTPUT", _DEFAULT_OUTPUT))
    try:
        payload = derive(
            _load(probe_path, "Tool Gateway probe"),
            _load(staging_path, "staging evidence"),
        )
    except SearchEvidenceError as exc:
        raise SystemExit(f"Tool Gateway search evidence failed: {exc}") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

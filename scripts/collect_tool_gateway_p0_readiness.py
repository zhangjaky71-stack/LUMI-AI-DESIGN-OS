#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_DEFAULT_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-readiness.json"
_MAX_RESPONSE_BYTES = 64 * 1024


class ReadinessEvidenceError(RuntimeError):
    pass


def _base_url() -> str:
    value = os.getenv("LUMI_TOOL_GATEWAY_URL", "")
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise ReadinessEvidenceError("LUMI_TOOL_GATEWAY_URL is invalid") from exc
    if parsed.scheme != "http" or not parsed.hostname:
        raise ReadinessEvidenceError(
            "LUMI_TOOL_GATEWAY_URL must be private HTTP service discovery URL"
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ReadinessEvidenceError("LUMI_TOOL_GATEWAY_URL is invalid")
    return value.rstrip("/")


def collect() -> dict[str, Any]:
    url = f"{_base_url()}/health/ready"
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": "LUMI-P0-Evidence/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10.0) as response:
            status = int(response.status)
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raw = exc.read(_MAX_RESPONSE_BYTES + 1)
        raise ReadinessEvidenceError(
            f"Tool Gateway readiness returned HTTP {int(exc.code)}: "
            f"{raw[:2000].decode('utf-8', errors='replace')}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ReadinessEvidenceError("Tool Gateway readiness is unavailable") from exc
    if status != 200:
        raise ReadinessEvidenceError(f"Tool Gateway readiness returned HTTP {status}")
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ReadinessEvidenceError("Tool Gateway readiness response exceeded limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadinessEvidenceError("Tool Gateway readiness returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ReadinessEvidenceError("Tool Gateway readiness must be an object")

    expected = {
        "service": "tool-gateway",
        "status": "ok",
        "adapter_count": 8,
        "runtime_binding_count": 4,
        "missing_adapters": [],
        "missing_runtime_bindings": [],
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ReadinessEvidenceError(
                f"Tool Gateway readiness mismatch for {key}: {payload.get(key)!r}"
            )
    return {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "http_status": status,
        "url_path": "/health/ready",
        "response": payload,
    }


def main() -> int:
    output = Path(os.getenv("LUMI_READINESS_EVIDENCE_OUTPUT", _DEFAULT_OUTPUT))
    try:
        payload = collect()
    except ReadinessEvidenceError as exc:
        raise SystemExit(f"Tool Gateway readiness evidence failed: {exc}") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

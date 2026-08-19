#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from lumi_tool_gateway.contracts import ToolPermissionContext, ToolRequest, canonical_json_bytes
from lumi_tool_gateway.http_transport import (
    INVOKE_PATH,
    decode_tool_result,
    encode_tool_request,
    sign_internal_request,
)

_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_DEFAULT_TIMEOUT_SECONDS = 150.0
_ALL_PERMISSIONS = frozenset(
    {
        "tool.web.search",
        "tool.web.fetch",
        "tool.project.query",
        "tool.asset.read",
        "tool.asset.write-derived",
        "tool.artifact.query",
        "tool.media.inspect",
        "tool.sandbox.execute",
    }
)


class ProbeError(RuntimeError):
    pass


class ToolGatewayProbeClient:
    def __init__(self, *, base_url: str, auth_secret: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ProbeError("LUMI_TOOL_GATEWAY_URL must be private HTTP service discovery URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProbeError("LUMI_TOOL_GATEWAY_URL is invalid")
        if len(auth_secret) < 32 or len(auth_secret) > 8192 or "\x00" in auth_secret:
            raise ProbeError("LUMI_TOOL_GATEWAY_AUTH_SECRET is invalid")
        self.base_url = base_url.rstrip("/")
        self.auth_secret = auth_secret

    async def invoke(self, request: ToolRequest) -> dict[str, Any]:
        return await asyncio.to_thread(self._invoke_sync, request)

    def _invoke_sync(self, request: ToolRequest) -> dict[str, Any]:
        body = canonical_json_bytes(encode_tool_request(request))
        auth = sign_internal_request(
            secret=self.auth_secret,
            service="agent-runtime",
            method="POST",
            path=INVOKE_PATH,
            body=body,
        )
        outbound = urllib.request.Request(
            f"{self.base_url}{INVOKE_PATH}",
            data=body,
            method="POST",
            headers={
                **auth.as_dict(),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(outbound, timeout=_DEFAULT_TIMEOUT_SECONDS) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            raw = exc.read(_MAX_RESPONSE_BYTES + 1)
            raise ProbeError(
                f"Tool Gateway {request.name} returned HTTP {int(exc.code)}: "
                f"{raw[:2000].decode('utf-8', errors='replace')}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProbeError(f"Tool Gateway {request.name} is unavailable") from exc
        if status != 200:
            raise ProbeError(f"Tool Gateway {request.name} returned HTTP {status}")
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ProbeError(f"Tool Gateway {request.name} response exceeded probe limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProbeError(f"Tool Gateway {request.name} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ProbeError(f"Tool Gateway {request.name} response must be an object")
        result = decode_tool_result(payload)
        return {
            "tool_call_id": str(result.tool_call_id),
            "status": str(result.status.value),
            "resolved_name": result.resolved_name,
            "resolved_version": result.resolved_version,
            "summary": result.summary,
            "resource_refs": list(result.resource_refs),
            "truncated": result.truncated,
            "full_result_ref": result.full_result_ref,
            "replayed": result.replayed,
            "approval_id": result.approval_id,
            "error_code": result.error_code,
            "data": result.data,
        }


def _required_env(name: str, *, max_length: int = 4096) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise ProbeError(f"{name} is required")
    return value


def _uuid_env(name: str) -> UUID:
    raw = _required_env(name, max_length=36)
    try:
        return UUID(raw)
    except ValueError as exc:
        raise ProbeError(f"{name} must be a UUID") from exc


def _permission_context(organization_id: UUID) -> ToolPermissionContext:
    return ToolPermissionContext(
        organization_id=organization_id,
        actor_id="staging-p0-probe",
        granted_permissions=_ALL_PERMISSIONS,
        agent_allow_patterns=("*",),
        organization_allow_patterns=("*",),
    )


def _request(
    *,
    organization_id: UUID,
    agent_run_id: UUID,
    task_id: UUID,
    name: str,
    arguments: dict[str, Any],
    trace_id: str,
    idempotency_key: str | None = None,
) -> ToolRequest:
    return ToolRequest(
        tool_call_id=uuid4(),
        organization_id=organization_id,
        agent_run_id=agent_run_id,
        task_id=task_id,
        actor_agent="staging-p0-probe",
        name=name,
        version="1.0.0",
        arguments=arguments,
        purpose="Production-like NODE-73 Tool Gateway P0 acceptance probe.",
        permission_context=_permission_context(organization_id),
        idempotency_key=idempotency_key,
        trace_id=trace_id,
    )


def _first_ref(result: dict[str, Any], prefix: str) -> str | None:
    refs = result.get("resource_refs")
    if not isinstance(refs, list):
        return None
    for value in refs:
        if isinstance(value, str) and value.startswith(prefix):
            return value
    return None


async def run_probe() -> dict[str, Any]:
    organization_id = _uuid_env("LUMI_PROBE_ORGANIZATION_ID")
    agent_run_id = _uuid_env("LUMI_PROBE_AGENT_RUN_ID")
    task_id = _uuid_env("LUMI_PROBE_TASK_ID")
    source_asset_id = _uuid_env("LUMI_PROBE_SOURCE_ASSET_ID")
    artifact_id = _uuid_env("LUMI_PROBE_ARTIFACT_ID")
    search_query = os.getenv("LUMI_PROBE_SEARCH_QUERY", "LUMI design systems")
    fetch_url = os.getenv("LUMI_PROBE_FETCH_URL", "https://example.com/")
    idempotency_key = _required_env("LUMI_PROBE_DERIVED_IDEMPOTENCY_KEY", max_length=256)
    trace_prefix = os.getenv("LUMI_PROBE_TRACE_PREFIX", f"node73-{uuid4()}")

    client = ToolGatewayProbeClient(
        base_url=_required_env("LUMI_TOOL_GATEWAY_URL"),
        auth_secret=_required_env("LUMI_TOOL_GATEWAY_AUTH_SECRET", max_length=8192),
    )

    definitions: list[tuple[str, dict[str, Any], str | None]] = [
        ("web.search", {"query": search_query, "limit": 5}, None),
        ("web.fetch", {"url": fetch_url}, None),
        ("project.query", {"query": "project.summary"}, None),
        ("asset.read", {"asset_id": str(source_asset_id)}, None),
        ("artifact.query", {"artifact_id": str(artifact_id)}, None),
        ("media.inspect", {"asset_id": str(source_asset_id)}, None),
        (
            "asset.write-derived",
            {
                "source_asset_id": str(source_asset_id),
                "artifact_ref": f"artifact://{artifact_id}",
                "metadata": {"probe": "node73", "variant": "staging-e2e"},
            },
            idempotency_key,
        ),
        (
            "sandbox.execute",
            {"command": ["python", "-c", "print('LUMI-P0-SANDBOX-OK')"]},
            f"{idempotency_key}-sandbox",
        ),
    ]

    calls: dict[str, Any] = {}
    first_write_request: ToolRequest | None = None
    for index, (name, arguments, idem) in enumerate(definitions, start=1):
        request = _request(
            organization_id=organization_id,
            agent_run_id=agent_run_id,
            task_id=task_id,
            name=name,
            arguments=arguments,
            trace_id=f"{trace_prefix}-{index}-{name}",
            idempotency_key=idem,
        )
        result = await client.invoke(request)
        calls[name] = {
            "request": {
                "tool_call_id": str(request.tool_call_id),
                "trace_id": request.trace_id,
                "idempotency_key_present": request.idempotency_key is not None,
            },
            "result": result,
        }
        if name == "asset.write-derived":
            first_write_request = request

    if first_write_request is None:
        raise ProbeError("derived asset probe request was not created")

    replay_request = _request(
        organization_id=organization_id,
        agent_run_id=agent_run_id,
        task_id=task_id,
        name="asset.write-derived",
        arguments=dict(first_write_request.arguments),
        trace_id=f"{trace_prefix}-replay-asset.write-derived",
        idempotency_key=idempotency_key,
    )
    replay_result = await client.invoke(replay_request)
    first_write_result = calls["asset.write-derived"]["result"]
    first_asset_ref = _first_ref(first_write_result, "asset://")
    replay_asset_ref = _first_ref(replay_result, "asset://")

    offload_request = _request(
        organization_id=organization_id,
        agent_run_id=agent_run_id,
        task_id=task_id,
        name="sandbox.execute",
        arguments={
            "command": [
                "python",
                "-c",
                "import sys; sys.stdout.write('LUMI-P0-' + ('x' * 70000))",
            ]
        },
        trace_id=f"{trace_prefix}-offload-sandbox.execute",
        idempotency_key=f"{idempotency_key}-sandbox-offload",
    )
    offload_result = await client.invoke(offload_request)
    offload_ref = offload_result.get("full_result_ref")
    if not isinstance(offload_ref, str) or not offload_ref.startswith("s3ref://"):
        raise ProbeError("oversized sandbox result did not produce a durable s3ref:// full_result_ref")
    if offload_result.get("truncated") is not True:
        raise ProbeError("oversized sandbox result was not marked truncated")

    return {
        "schema_version": 1,
        "probe_id": str(uuid4()),
        "caller_service": "agent-runtime",
        "captured_at": datetime.now(UTC).isoformat(),
        "scope": {
            "organization_id": str(organization_id),
            "agent_run_id": str(agent_run_id),
            "task_id": str(task_id),
            "source_asset_id": str(source_asset_id),
            "artifact_id": str(artifact_id),
        },
        "calls": calls,
        "idempotent_replay": {
            "first_tool_call_id": calls["asset.write-derived"]["request"]["tool_call_id"],
            "replay_tool_call_id": str(replay_request.tool_call_id),
            "first_asset_ref": first_asset_ref,
            "replay_asset_ref": replay_asset_ref,
            "replayed": replay_result.get("replayed"),
            "same_asset_ref": bool(first_asset_ref and first_asset_ref == replay_asset_ref),
        },
        "result_offload": {
            "tool": "sandbox.execute",
            "tool_call_id": str(offload_request.tool_call_id),
            "trace_id": offload_request.trace_id,
            "result_ref": offload_ref,
            "inline_data_present": offload_result.get("data") is not None,
            "truncated": offload_result.get("truncated"),
            "result": offload_result,
        },
    }


def main() -> int:
    output = Path(os.getenv("LUMI_PROBE_OUTPUT", "reports/tool-gateway-p0-probe.json"))
    payload = asyncio.run(run_probe())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

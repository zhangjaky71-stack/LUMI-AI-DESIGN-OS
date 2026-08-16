from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP_ROOT = ROOT / "services/tool-gateway/src/lumi_tool_gateway/mcp"


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing NODE-26 marker: {needle}")


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: forbidden NODE-26 marker: {needle}")


def validate_import_boundary() -> None:
    forbidden_modules = {
        "httpx",
        "requests",
        "aiohttp",
        "urllib3",
        "subprocess",
        "asyncpg",
        "sqlalchemy",
        "boto3",
        "docker",
        "mcp",
    }
    for path in sorted(MCP_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = {alias.name.split(".", 1)[0] for alias in node.names}
                bad = modules & forbidden_modules
                if bad:
                    raise SystemExit(f"{path}: privileged MCP dependency: {sorted(bad)}")
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".", 1)[0]
                if module in forbidden_modules:
                    raise SystemExit(f"{path}: privileged MCP dependency: {module}")


def validate_execution_cache_boundary() -> None:
    path = MCP_ROOT / "client.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "MCPClient":
            for method in node.body:
                if (
                    isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and method.name == "call_tool"
                ):
                    source = ast.get_source_segment(text, method) or ""
                    if "discovery_cache" in source:
                        raise SystemExit("MCP tools/call must never use discovery cache")
                    return
    raise SystemExit("MCPClient.call_tool not found")


def validate_runtime_contracts() -> None:
    from lumi_tool_gateway.mcp.contracts import (
        MCP_PROTOCOL_2026_07_28,
        MCPServerDefinition,
        MCPTransportKind,
        MCPTrustLevel,
    )

    if MCP_PROTOCOL_2026_07_28 != "2026-07-28":
        raise SystemExit("MCP modern protocol baseline drifted")
    try:
        MCPServerDefinition(
            server_id="bad-modern",
            name="bad",
            base_url="https://example.com/mcp",
            transport=MCPTransportKind.LEGACY_HTTP_SSE,
            enabled=True,
            approved=True,
            trust_level=MCPTrustLevel.RESTRICTED,
            organization_id=None,
            allowed_tool_patterns=("*",),
            protocol_versions=(MCP_PROTOCOL_2026_07_28,),
        )
    except ValueError as exc:
        if "MCP_2026_TRANSPORT_INVALID" not in str(exc):
            raise
    else:
        raise SystemExit("2026 protocol accepted legacy HTTP/SSE transport")

    try:
        MCPServerDefinition(
            server_id="cleartext",
            name="bad",
            base_url="http://example.com/mcp",
            transport=MCPTransportKind.STREAMABLE_HTTP,
            enabled=True,
            approved=True,
            trust_level=MCPTrustLevel.RESTRICTED,
            organization_id=None,
            allowed_tool_patterns=("*",),
            protocol_versions=(MCP_PROTOCOL_2026_07_28,),
        )
    except ValueError as exc:
        if "MCP_SERVER_TLS_REQUIRED" not in str(exc):
            raise
    else:
        raise SystemExit("cleartext MCP endpoint accepted")


def validate_gap_ledger() -> None:
    ledger = json.loads(
        (ROOT / "reports/nodes/NODE-26/gap-ledger.json").read_text(encoding="utf-8")
    )
    gaps = ledger.get("gaps")
    if not isinstance(gaps, list) or len(gaps) != 7:
        raise SystemExit("NODE-26 gap ledger must contain exactly 7 gaps")
    ids = [item.get("id") for item in gaps]
    if len(ids) != len(set(ids)):
        raise SystemExit("NODE-26 gap IDs must be unique")


def main() -> int:
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/contracts.py",
        'MCP_PROTOCOL_2026_07_28 = "2026-07-28"',
        'MCP_PROTOCOL_2025_11_25 = "2025-11-25"',
        "MCP_SERVER_TLS_REQUIRED",
        "MCP_2026_TRANSPORT_INVALID",
        "approved: bool",
        "organization_id: UUID | None",
        "allowed_tool_patterns",
        "MCP_WRITE_TOOL_IDEMPOTENCY_REQUIRED",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/registry.py",
        "self.ssrf_policy.validate(definition.base_url)",
        "return self.ssrf_policy.validate(definition.base_url)",
        "MCP_SERVER_NOT_APPROVED",
        "MCP_SERVER_DISABLED",
        "MCP_SERVER_TENANT_DENIED",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/client.py",
        'method="server/discover"',
        'method="tools/list"',
        'method="tools/call"',
        '"MCP-Protocol-Version": protocol_version',
        '"Mcp-Method": method',
        'headers["Mcp-Name"] = name',
        '"io.modelcontextprotocol/protocolVersion": protocol_version',
        '"io.modelcontextprotocol/clientCapabilities"',
        '"io.modelcontextprotocol/clientInfo"',
        "_cache_hints_2026",
        'cache_scope not in {"private", "public"}',
        "ttl_ms < 0",
        "input_required result missing inputRequests/requestState",
    )
    forbid(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/client.py",
        "Mcp-Session-Id",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/legacy.py",
        'method": "initialize"',
        'method": "notifications/initialized"',
        'headers["Mcp-Session-Id"] = session.session_id',
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/auth.py",
        "server_id: str",
        "auth.server_id != server.server_id",
        '"mcp-protocol-version"',
        '"mcp-method"',
        '"mcp-name"',
        '"mcp-session-id"',
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/mapping.py",
        "policy = policy_by_name.get(tool.remote_name)",
        "if policy is None:",
        "MCP_TOOL_NAMESPACE_COLLISION",
        "unsupported schema keywords",
        "x-mcp-header",
        "risk=policy.risk",
        "idempotency=policy.idempotency",
    )
    forbid(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/mapping.py",
        "tool.annotations",
        "readOnlyHint",
        "destructiveHint",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/adapter.py",
        "definition.runtime != ToolRuntime.MCP",
        "MCPInputRequiredError",
        'result.result_type == "input_required"',
        "request_keys=tuple(sorted",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/transport.py",
        "target: ValidatedTarget",
        "MCPHTTPTransport(Protocol)",
    )
    require(
        "services/tool-gateway/pyproject.toml",
        "dependencies = []",
    )
    validate_import_boundary()
    validate_execution_cache_boundary()
    validate_runtime_contracts()
    validate_gap_ledger()
    print("NODE26_MCP_ARCHITECTURE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

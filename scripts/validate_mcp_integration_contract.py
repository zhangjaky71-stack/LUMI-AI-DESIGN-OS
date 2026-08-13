from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_ROOT = ROOT / "services/tool-gateway/src/lumi_tool_gateway/mcp"


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing NODE-26 contract marker: {needle}")


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
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = {alias.name.split(".", 1)[0] for alias in node.names}
                bad = modules & forbidden_modules
                if bad:
                    raise SystemExit(f"{path}: MCP core bypass dependency: {sorted(bad)}")
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".", 1)[0]
                if module in forbidden_modules:
                    raise SystemExit(f"{path}: MCP core bypass dependency: {module}")


def validate_execution_cache_boundary() -> None:
    path = MCP_ROOT / "client.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "MCPClient":
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name == "call_tool":
                    source = ast.get_source_segment(path.read_text(encoding="utf-8"), method) or ""
                    if "discovery_cache" in source:
                        raise SystemExit("tools/call must never use MCP discovery result cache")
                    return
    raise SystemExit("MCPClient.call_tool not found")


def main() -> int:
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/contracts.py",
        'MCP_PROTOCOL_2026_07_28 = "2026-07-28"',
        'MCP_PROTOCOL_2025_11_25 = "2025-11-25"',
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
        "auth.organization_id != organization_id",
        "MCP_PROTOCOL_2025_11_25",
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
        "services/tool-gateway/src/lumi_tool_gateway/mcp/auth.py",
        '"mcp-protocol-version"',
        '"mcp-method"',
        '"mcp-name"',
        '"mcp-session-id"',
        "organization_id: UUID",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/transport.py",
        "target: ValidatedTarget",
        "MCPHTTPTransport(Protocol)",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/cache.py",
        "Caches discovery/tool metadata only",
        "organization_id",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/integration.py",
        "MCPIntegrationBuilder",
        "map_approved_tools",
        "MCPToolAdapter",
    )
    require(
        "services/tool-gateway/pyproject.toml",
        "dependencies = []",
    )
    forbid(
        "services/tool-gateway/src/lumi_tool_gateway/mcp/adapter.py",
        "base_url",
        "Authorization",
        "Cookie",
    )
    validate_import_boundary()
    validate_execution_cache_boundary()
    print("NODE-26 MCP Integration architecture/security contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

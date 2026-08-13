from __future__ import annotations

import json
import re
from typing import Any

from ..contracts import ToolDefinition, ToolRuntime
from .contracts import MCPDiscoveredTool, MCPServerDefinition, MCPToolPolicy
from .errors import MCPPolicyDeniedError, MCPSchemaInvalidError
from .registry import MCPServerRegistry

_SEGMENT = re.compile(r"[^a-z0-9_-]+")


class MCPToolMapper:
    """Maps discovered MCP metadata only when a LUMI admin policy approves it."""

    def map_approved_tools(
        self,
        *,
        server: MCPServerDefinition,
        discovered: tuple[MCPDiscoveredTool, ...],
        policies: tuple[MCPToolPolicy, ...],
    ) -> tuple[ToolDefinition, ...]:
        policy_by_name = {
            policy.remote_tool_name: policy
            for policy in policies
            if policy.server_id == server.server_id
        }
        mapped: list[ToolDefinition] = []
        used_names: dict[str, str] = {}
        for tool in discovered:
            if not MCPServerRegistry.tool_allowed(server, tool.remote_name):
                continue
            policy = policy_by_name.get(tool.remote_name)
            if policy is None:
                continue
            definition = self.map_tool(server=server, tool=tool, policy=policy)
            previous = used_names.get(definition.name)
            if previous is not None and previous != tool.remote_name:
                raise MCPPolicyDeniedError(
                    f"MCP_TOOL_NAMESPACE_COLLISION:{previous}:{tool.remote_name}"
                )
            used_names[definition.name] = tool.remote_name
            mapped.append(definition)
        return tuple(mapped)

    def map_tool(
        self,
        *,
        server: MCPServerDefinition,
        tool: MCPDiscoveredTool,
        policy: MCPToolPolicy,
    ) -> ToolDefinition:
        if policy.server_id != server.server_id:
            raise MCPPolicyDeniedError("MCP_TOOL_POLICY_SERVER_MISMATCH")
        if policy.remote_tool_name != tool.remote_name:
            raise MCPPolicyDeniedError("MCP_TOOL_POLICY_NAME_MISMATCH")
        if not MCPServerRegistry.tool_allowed(server, tool.remote_name):
            raise MCPPolicyDeniedError("MCP_TOOL_NOT_ALLOWED_BY_SERVER_POLICY")
        self._validate_schema(tool.input_schema, path="$.inputSchema")
        if tool.output_schema is not None:
            self._validate_schema(tool.output_schema, path="$.outputSchema")
        output_schema = tool.output_schema or {
            "type": ["object", "array", "string", "number", "boolean", "null"]
        }
        name = mcp_lumi_tool_name(server.server_id, tool.remote_name)
        return ToolDefinition(
            name=name,
            version="1.0.0",
            description=tool.description or f"MCP tool {tool.remote_name}",
            input_schema=tool.input_schema,
            output_schema=output_schema,
            risk=policy.risk,
            idempotency=policy.idempotency,
            permissions=policy.permissions,
            runtime=ToolRuntime.MCP,
            timeout_seconds=policy.timeout_seconds,
            max_inline_output_bytes=policy.max_inline_output_bytes,
            sensitive_fields=policy.sensitive_fields,
        )

    def _validate_schema(self, schema: dict[str, Any], *, path: str) -> None:
        try:
            encoded = json.dumps(schema, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise MCPSchemaInvalidError(f"{path}: non-JSON schema") from exc
        if len(encoded.encode("utf-8")) > 128 * 1024:
            raise MCPSchemaInvalidError(f"{path}: schema too large")
        self._walk_schema(schema, path=path, depth=0)

    def _walk_schema(self, value: Any, *, path: str, depth: int) -> None:
        if depth > 32:
            raise MCPSchemaInvalidError(f"{path}: schema too deep")
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise MCPSchemaInvalidError(f"{path}: non-string schema key")
                if key.lower() == "x-mcp-header":
                    raise MCPSchemaInvalidError(
                        f"{path}: untrusted x-mcp-header mapping is disabled"
                    )
                self._walk_schema(child, path=f"{path}.{key}", depth=depth + 1)
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                self._walk_schema(
                    child,
                    path=f"{path}[{index}]",
                    depth=depth + 1,
                )
            return
        if value is None or isinstance(value, (str, int, float, bool)):
            return
        raise MCPSchemaInvalidError(f"{path}: unsupported schema value")


def mcp_lumi_tool_name(server_id: str, remote_tool_name: str) -> str:
    segments = []
    for raw in remote_tool_name.split("."):
        normalized = _SEGMENT.sub("-", raw.lower()).strip("-_")
        if not normalized:
            raise MCPPolicyDeniedError("MCP_TOOL_NAME_CANNOT_NAMESPACE")
        if normalized[0].isdigit():
            normalized = f"t-{normalized}"
        segments.append(normalized[:63])
    return ".".join(("mcp", server_id, *segments))

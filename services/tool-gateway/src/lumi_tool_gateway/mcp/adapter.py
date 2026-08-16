from __future__ import annotations

from typing import Any

from ..contracts import ToolAdapterOutput, ToolDefinition, ToolRequest, ToolRuntime
from .client import MCPClient
from .errors import MCPError, MCPInputRequiredError, MCPPolicyDeniedError


class MCPToolAdapter:
    """Adapts one approved MCP remote tool behind the NODE-25 ToolAdapter contract."""

    def __init__(
        self,
        *,
        client: MCPClient,
        server_id: str,
        remote_tool_name: str,
        lumi_tool_name: str,
        protocol_version: str,
    ) -> None:
        self.client = client
        self.server_id = server_id
        self.remote_tool_name = remote_tool_name
        self.lumi_tool_name = lumi_tool_name
        self.protocol_version = protocol_version

    async def invoke(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolAdapterOutput:
        if definition.runtime != ToolRuntime.MCP:
            raise MCPPolicyDeniedError("MCP_ADAPTER_RUNTIME_MISMATCH")
        if definition.name != self.lumi_tool_name:
            raise MCPPolicyDeniedError("MCP_ADAPTER_TOOL_MAPPING_MISMATCH")
        result = await self.client.call_tool(
            self.server_id,
            organization_id=request.organization_id,
            remote_tool_name=self.remote_tool_name,
            arguments=request.arguments,
            protocol_version=self.protocol_version,
        )
        if result.result_type == "input_required":
            requests = result.input_requests or {}
            raise MCPInputRequiredError(
                server_id=self.server_id,
                tool_name=self.remote_tool_name,
                request_keys=tuple(sorted(str(key) for key in requests)),
                request_state_present=result.request_state is not None,
            )
        if result.result_type != "complete":
            raise MCPError("unsupported MCP result type")
        if result.is_error:
            raise MCPError("MCP tool reported a sanitized execution error")
        if result.structured_content_present:
            data: Any = result.structured_content
        else:
            data = {"content": list(result.content)}
        return ToolAdapterOutput(
            data=data,
            summary=_summary(result.content),
            resource_refs=_resource_refs(result.content),
        )


def _summary(content: tuple[dict[str, Any], ...]) -> str:
    parts: list[str] = []
    for item in content:
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(str(item["text"]))
            if sum(len(part) for part in parts) >= 4000:
                break
    text = "\n".join(parts)
    return text[:4000]


def _resource_refs(content: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for item in content:
        uri = item.get("uri")
        if isinstance(uri, str) and uri and len(uri) <= 2048:
            refs.append(uri)
        resource = item.get("resource")
        if isinstance(resource, dict):
            resource_uri = resource.get("uri")
            if isinstance(resource_uri, str) and resource_uri and len(resource_uri) <= 2048:
                refs.append(resource_uri)
    return tuple(dict.fromkeys(refs))

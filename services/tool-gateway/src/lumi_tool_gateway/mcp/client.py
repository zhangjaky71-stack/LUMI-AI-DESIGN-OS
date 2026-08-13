from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from .auth import MCPCredentialProvider, NoAuthCredentialProvider
from .cache import MCPDiscoveryCache
from .contracts import (
    MCP_PROTOCOL_2025_11_25,
    MCP_PROTOCOL_2026_07_28,
    MCPCallResult,
    MCPClientIdentity,
    MCPDiscoveredTool,
    MCPDiscoveryResult,
    MCPServerDefinition,
)
from .errors import (
    MCPAuthFailedError,
    MCPError,
    MCPPolicyDeniedError,
    MCPProtocolMismatchError,
    MCPSchemaInvalidError,
    MCPServerUnavailableError,
    MCPToolNotFoundError,
)
from .legacy import LegacyMCPClient
from .registry import MCPServerRegistry
from .transport import MCPHTTPResponse, MCPHTTPTransport


class MCPClient:
    """MCP client with a stateless 2026 path and isolated legacy compatibility path."""

    def __init__(
        self,
        *,
        registry: MCPServerRegistry,
        transport: MCPHTTPTransport,
        credentials: MCPCredentialProvider | None = None,
        identity: MCPClientIdentity | None = None,
        discovery_cache: MCPDiscoveryCache | None = None,
    ) -> None:
        self.registry = registry
        self.transport = transport
        self.credentials = credentials or NoAuthCredentialProvider()
        self.identity = identity or MCPClientIdentity()
        self.discovery_cache = discovery_cache or MCPDiscoveryCache()
        self.legacy = LegacyMCPClient(
            registry=registry,
            transport=transport,
            credentials=self.credentials,
            identity=self.identity,
        )

    async def discover_tools(
        self,
        server_id: str,
        *,
        organization_id: UUID,
        force: bool = False,
    ) -> MCPDiscoveryResult:
        server = self.registry.resolve(server_id, organization_id=organization_id)
        if not force:
            cached = self.discovery_cache.get(
                server_id,
                organization_id=organization_id,
            )
            if cached is not None:
                return cached

        if MCP_PROTOCOL_2026_07_28 not in server.protocol_versions:
            result = await self.legacy.discover_tools(
                server,
                organization_id=organization_id,
            )
            self.discovery_cache.put(
                server_id,
                organization_id=organization_id,
                result=result,
                ttl_seconds=result.ttl_seconds,
            )
            return result

        try:
            discovery = await self._request_2026(
                server,
                organization_id=organization_id,
                method="server/discover",
                params={},
                name=None,
                protocol_version=MCP_PROTOCOL_2026_07_28,
            )
        except (MCPProtocolMismatchError, MCPToolNotFoundError):
            if MCP_PROTOCOL_2025_11_25 not in server.protocol_versions:
                raise
            result = await self.legacy.discover_tools(
                server,
                organization_id=organization_id,
            )
            self.discovery_cache.put(
                server_id,
                organization_id=organization_id,
                result=result,
                ttl_seconds=result.ttl_seconds,
            )
            return result

        raw_versions = discovery.get("supportedVersions")
        if not isinstance(raw_versions, list) or not all(
            isinstance(item, str) for item in raw_versions
        ):
            raise MCPProtocolMismatchError("server/discover supportedVersions invalid")
        protocol_version = self.registry.negotiate_protocol(
            server,
            tuple(raw_versions),
        )
        if protocol_version == MCP_PROTOCOL_2025_11_25:
            result = await self.legacy.discover_tools(
                server,
                organization_id=organization_id,
            )
            self.discovery_cache.put(
                server_id,
                organization_id=organization_id,
                result=result,
                ttl_seconds=result.ttl_seconds,
            )
            return result

        tools, list_ttl, cache_scope = await self._list_tools_2026(
            server,
            organization_id=organization_id,
            protocol_version=protocol_version,
        )
        discover_ttl = _ttl_seconds(discovery, default=server.discovery_ttl_seconds)
        ttl = min(server.discovery_ttl_seconds, discover_ttl, list_ttl)
        meta = discovery.get("_meta")
        server_info: dict[str, Any] = {}
        if isinstance(meta, dict):
            candidate = meta.get("io.modelcontextprotocol/serverInfo")
            if isinstance(candidate, dict):
                server_info = dict(candidate)
        result = MCPDiscoveryResult(
            protocol_version=protocol_version,
            tools=tools,
            ttl_seconds=ttl,
            cache_scope=cache_scope,
            server_info=server_info,
        )
        self.discovery_cache.put(
            server_id,
            organization_id=organization_id,
            result=result,
            ttl_seconds=ttl,
        )
        return result

    async def call_tool(
        self,
        server_id: str,
        *,
        organization_id: UUID,
        remote_tool_name: str,
        arguments: dict[str, Any],
        protocol_version: str,
    ) -> MCPCallResult:
        server = self.registry.resolve(server_id, organization_id=organization_id)
        if not self.registry.tool_allowed(server, remote_tool_name):
            raise MCPPolicyDeniedError("MCP_TOOL_NOT_ALLOWED_BY_SERVER_POLICY")
        if protocol_version == MCP_PROTOCOL_2025_11_25:
            return await self.legacy.call_tool(
                server,
                organization_id=organization_id,
                remote_tool_name=remote_tool_name,
                arguments=arguments,
            )
        if protocol_version != MCP_PROTOCOL_2026_07_28:
            raise MCPProtocolMismatchError("unsupported MCP call protocol")
        result = await self._request_2026(
            server,
            organization_id=organization_id,
            method="tools/call",
            params={"name": remote_tool_name, "arguments": arguments},
            name=remote_tool_name,
            protocol_version=protocol_version,
        )
        return _parse_call_result_2026(result)

    async def _list_tools_2026(
        self,
        server: MCPServerDefinition,
        *,
        organization_id: UUID,
        protocol_version: str,
    ) -> tuple[tuple[MCPDiscoveredTool, ...], int, str]:
        tools: list[MCPDiscoveredTool] = []
        cursor: str | None = None
        ttl = server.discovery_ttl_seconds
        cache_scope = "private"
        for _ in range(10):
            params: dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor
            result = await self._request_2026(
                server,
                organization_id=organization_id,
                method="tools/list",
                params=params,
                name=None,
                protocol_version=protocol_version,
            )
            raw_tools = result.get("tools")
            if not isinstance(raw_tools, list):
                raise MCPProtocolMismatchError("tools/list missing tools array")
            for raw_tool in raw_tools:
                tools.append(_parse_discovered_tool(raw_tool))
                if len(tools) > 512:
                    raise MCPProtocolMismatchError("MCP tool catalog exceeds safe limit")
            ttl = min(ttl, _ttl_seconds(result, default=server.discovery_ttl_seconds))
            raw_scope = result.get("cacheScope")
            if isinstance(raw_scope, str) and raw_scope in {"private", "public"}:
                cache_scope = raw_scope
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                return tuple(tools), ttl, cache_scope
            if not isinstance(next_cursor, str) or not next_cursor:
                raise MCPProtocolMismatchError("tools/list nextCursor invalid")
            cursor = next_cursor
        raise MCPProtocolMismatchError("MCP tools/list pagination limit exceeded")

    async def _request_2026(
        self,
        server: MCPServerDefinition,
        *,
        organization_id: UUID,
        method: str,
        params: dict[str, Any],
        name: str | None,
        protocol_version: str,
    ) -> dict[str, Any]:
        request_id = str(uuid4())
        request_params = dict(params)
        request_params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": protocol_version,
            "io.modelcontextprotocol/clientCapabilities": dict(
                self.identity.capabilities
            ),
            "io.modelcontextprotocol/clientInfo": {
                "name": self.identity.name,
                "version": self.identity.version,
            },
        }
        body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": request_params,
        }
        auth = await self.credentials.credentials_for(
            server,
            organization_id=organization_id,
        )
        if auth.organization_id != organization_id:
            raise MCPAuthFailedError("MCP credential tenant mismatch")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": protocol_version,
            "Mcp-Method": method,
            **auth.headers,
        }
        if name is not None:
            headers["Mcp-Name"] = name
        response = await self.transport.post(
            target=self.registry.runtime_target(
                server.server_id,
                organization_id=organization_id,
            ),
            headers=headers,
            body=body,
            timeout_seconds=30.0,
        )
        return _validated_2026_result(response, request_id=request_id)


def _validated_2026_result(
    response: MCPHTTPResponse,
    *,
    request_id: str,
) -> dict[str, Any]:
    if response.status in {401, 403}:
        raise MCPAuthFailedError("MCP authentication failed")
    if response.status >= 500:
        raise MCPServerUnavailableError("MCP server unavailable")
    if response.status < 200 or response.status >= 300:
        raise MCPProtocolMismatchError("MCP HTTP response rejected")
    body = response.json_body
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        raise MCPProtocolMismatchError("invalid MCP JSON-RPC response")
    if body.get("id") != request_id:
        raise MCPProtocolMismatchError("MCP JSON-RPC response id mismatch")
    error = body.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if code == -32601:
            raise MCPToolNotFoundError("MCP method or tool not found")
        if code == -32020:
            raise MCPProtocolMismatchError("MCP header/body routing mismatch")
        raise MCPError("MCP server returned a sanitized JSON-RPC error")
    result = body.get("result")
    if not isinstance(result, dict):
        raise MCPProtocolMismatchError("MCP result object missing")
    result_type = result.get("resultType")
    if not isinstance(result_type, str):
        raise MCPProtocolMismatchError("2026 MCP resultType is required")
    return result


def _parse_discovered_tool(raw: Any) -> MCPDiscoveredTool:
    if not isinstance(raw, dict):
        raise MCPSchemaInvalidError("MCP tool descriptor must be an object")
    input_schema = raw.get("inputSchema")
    output_schema = raw.get("outputSchema")
    annotations = raw.get("annotations")
    try:
        return MCPDiscoveredTool(
            remote_name=str(raw.get("name", "")),
            description=str(raw.get("description", "")),
            input_schema=input_schema,
            output_schema=output_schema,
            annotations=annotations if isinstance(annotations, dict) else {},
        )
    except (TypeError, ValueError) as exc:
        raise MCPSchemaInvalidError("invalid MCP tool descriptor") from exc


def _parse_call_result_2026(result: dict[str, Any]) -> MCPCallResult:
    result_type = result.get("resultType")
    if not isinstance(result_type, str):
        raise MCPProtocolMismatchError("2026 MCP resultType missing")
    raw_content = result.get("content", [])
    if not isinstance(raw_content, list) or not all(
        isinstance(item, dict) for item in raw_content
    ):
        raise MCPProtocolMismatchError("MCP tool content invalid")
    input_requests = result.get("inputRequests")
    if input_requests is not None and not isinstance(input_requests, dict):
        raise MCPProtocolMismatchError("MCP inputRequests invalid")
    request_state = result.get("requestState")
    if request_state is not None and not isinstance(request_state, str):
        raise MCPProtocolMismatchError("MCP requestState invalid")
    return MCPCallResult(
        structured_content=result.get("structuredContent"),
        structured_content_present="structuredContent" in result,
        content=tuple(raw_content),
        is_error=bool(result.get("isError", False)),
        result_type=result_type,
        input_requests=input_requests,
        request_state=request_state,
    )


def _ttl_seconds(result: dict[str, Any], *, default: int) -> int:
    ttl_ms = result.get("ttlMs")
    if isinstance(ttl_ms, int) and ttl_ms >= 0:
        return max(1, min(default, max(1, ttl_ms // 1000)))
    return default

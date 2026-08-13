from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from .auth import MCPCredentialProvider
from .contracts import (
    MCP_PROTOCOL_2025_11_25,
    MCPCallResult,
    MCPClientIdentity,
    MCPDiscoveredTool,
    MCPDiscoveryResult,
    MCPServerDefinition,
)
from .errors import (
    MCPAuthFailedError,
    MCPError,
    MCPProtocolMismatchError,
    MCPSchemaInvalidError,
    MCPServerUnavailableError,
    MCPToolNotFoundError,
)
from .registry import MCPServerRegistry
from .transport import MCPHTTPResponse, MCPHTTPTransport


@dataclass(slots=True)
class _LegacySession:
    session_id: str | None
    protocol_version: str


class LegacyMCPClient:
    """Compatibility island for the 2025-11-25 initialize/session lifecycle."""

    def __init__(
        self,
        *,
        registry: MCPServerRegistry,
        transport: MCPHTTPTransport,
        credentials: MCPCredentialProvider,
        identity: MCPClientIdentity,
    ) -> None:
        self.registry = registry
        self.transport = transport
        self.credentials = credentials
        self.identity = identity
        self._sessions: dict[tuple[str, str], _LegacySession] = {}

    async def discover_tools(
        self,
        server: MCPServerDefinition,
        *,
        organization_id: UUID,
    ) -> MCPDiscoveryResult:
        session = await self._session(server, organization_id=organization_id)
        result = await self._request(
            server,
            organization_id=organization_id,
            session=session,
            method="tools/list",
            params={},
        )
        tools = _parse_tools(result)
        return MCPDiscoveryResult(
            protocol_version=session.protocol_version,
            tools=tools,
            ttl_seconds=server.discovery_ttl_seconds,
            cache_scope="private",
        )

    async def call_tool(
        self,
        server: MCPServerDefinition,
        *,
        organization_id: UUID,
        remote_tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPCallResult:
        session = await self._session(server, organization_id=organization_id)
        result = await self._request(
            server,
            organization_id=organization_id,
            session=session,
            method="tools/call",
            params={"name": remote_tool_name, "arguments": arguments},
        )
        return _parse_call_result(result, legacy=True)

    async def _session(
        self,
        server: MCPServerDefinition,
        *,
        organization_id: UUID,
    ) -> _LegacySession:
        key = (server.server_id, str(organization_id))
        existing = self._sessions.get(key)
        if existing is not None:
            return existing
        request_id = str(uuid4())
        response = await self._post(
            server,
            organization_id=organization_id,
            headers={
                "MCP-Protocol-Version": MCP_PROTOCOL_2025_11_25,
            },
            body={
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_2025_11_25,
                    "capabilities": {},
                    "clientInfo": {
                        "name": self.identity.name,
                        "version": self.identity.version,
                    },
                },
            },
        )
        result = _validated_result(response, request_id=request_id)
        protocol_version = result.get("protocolVersion")
        if protocol_version != MCP_PROTOCOL_2025_11_25:
            raise MCPProtocolMismatchError("legacy MCP protocol negotiation mismatch")
        session_id = _header(response.headers, "mcp-session-id") or None
        session = _LegacySession(
            session_id=session_id,
            protocol_version=MCP_PROTOCOL_2025_11_25,
        )
        self._sessions[key] = session
        notification_headers = {
            "MCP-Protocol-Version": MCP_PROTOCOL_2025_11_25,
        }
        if session_id:
            notification_headers["Mcp-Session-Id"] = session_id
        await self._post(
            server,
            organization_id=organization_id,
            headers=notification_headers,
            body={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
            allow_empty=True,
        )
        return session

    async def _request(
        self,
        server: MCPServerDefinition,
        *,
        organization_id: UUID,
        session: _LegacySession,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        request_id = str(uuid4())
        headers = {"MCP-Protocol-Version": session.protocol_version}
        if session.session_id:
            headers["Mcp-Session-Id"] = session.session_id
        response = await self._post(
            server,
            organization_id=organization_id,
            headers=headers,
            body={
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            },
        )
        return _validated_result(response, request_id=request_id)

    async def _post(
        self,
        server: MCPServerDefinition,
        *,
        organization_id: UUID,
        headers: dict[str, str],
        body: dict[str, Any],
        allow_empty: bool = False,
    ) -> MCPHTTPResponse:
        auth = await self.credentials.credentials_for(
            server,
            organization_id=organization_id,
        )
        if auth.organization_id != organization_id:
            raise MCPAuthFailedError("MCP credential tenant mismatch")
        merged = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **headers,
            **auth.headers,
        }
        response = await self.transport.post(
            target=self.registry.runtime_target(
                server.server_id,
                organization_id=organization_id,
            ),
            headers=merged,
            body=body,
            timeout_seconds=30.0,
        )
        _validate_http(response, allow_empty=allow_empty)
        return response


def _validate_http(response: MCPHTTPResponse, *, allow_empty: bool = False) -> None:
    if response.status in {401, 403}:
        raise MCPAuthFailedError("MCP authentication failed")
    if response.status >= 500:
        raise MCPServerUnavailableError("MCP server unavailable")
    if response.status < 200 or response.status >= 300:
        raise MCPProtocolMismatchError("MCP HTTP protocol response rejected")
    if response.json_body is None and not allow_empty:
        raise MCPProtocolMismatchError("MCP response body missing")


def _validated_result(
    response: MCPHTTPResponse,
    *,
    request_id: str,
) -> dict[str, Any]:
    body = response.json_body
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        raise MCPProtocolMismatchError("invalid MCP JSON-RPC response")
    if body.get("id") != request_id:
        raise MCPProtocolMismatchError("MCP JSON-RPC response id mismatch")
    error = body.get("error")
    if isinstance(error, dict):
        if error.get("code") == -32601:
            raise MCPToolNotFoundError("MCP method or tool not found")
        raise MCPError("MCP server returned a sanitized JSON-RPC error")
    result = body.get("result")
    if not isinstance(result, dict):
        raise MCPProtocolMismatchError("MCP result object missing")
    return result


def _parse_tools(result: dict[str, Any]) -> tuple[MCPDiscoveredTool, ...]:
    raw_tools = result.get("tools")
    if not isinstance(raw_tools, list):
        raise MCPProtocolMismatchError("MCP tools/list result missing tools")
    tools: list[MCPDiscoveredTool] = []
    for raw in raw_tools:
        if not isinstance(raw, dict):
            raise MCPSchemaInvalidError("MCP tool descriptor must be an object")
        try:
            tools.append(
                MCPDiscoveredTool(
                    remote_name=str(raw.get("name", "")),
                    description=str(raw.get("description", "")),
                    input_schema=raw.get("inputSchema"),
                    output_schema=raw.get("outputSchema"),
                    annotations=(
                        raw.get("annotations")
                        if isinstance(raw.get("annotations"), dict)
                        else {}
                    ),
                )
            )
        except (TypeError, ValueError) as exc:
            raise MCPSchemaInvalidError("invalid MCP tool descriptor") from exc
    return tuple(tools)


def _parse_call_result(
    result: dict[str, Any],
    *,
    legacy: bool,
) -> MCPCallResult:
    result_type = result.get("resultType", "complete" if legacy else None)
    if not isinstance(result_type, str):
        raise MCPProtocolMismatchError("MCP resultType missing or invalid")
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


def _header(headers: dict[str, str], name: str) -> str:
    lower = name.lower()
    for key, value in headers.items():
        if key.lower() == lower:
            return value
    return ""

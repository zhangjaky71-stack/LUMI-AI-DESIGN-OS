from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from lumi_tool_gateway.audit import MemoryAuditSink
from lumi_tool_gateway.contracts import (
    ApprovalDecision,
    ToolCallStatus,
    ToolIdempotency,
    ToolPermissionContext,
    ToolRequest,
    ToolRisk,
)
from lumi_tool_gateway.gateway import ToolGateway
from lumi_tool_gateway.mcp.auth import MCPRequestAuth
from lumi_tool_gateway.mcp.client import MCPClient
from lumi_tool_gateway.mcp.contracts import (
    MCP_PROTOCOL_2026_07_28,
    MCPServerDefinition,
    MCPToolPolicy,
    MCPTransportKind,
    MCPTrustLevel,
)
from lumi_tool_gateway.mcp.integration import MCPIntegrationBuilder
from lumi_tool_gateway.mcp.registry import MCPServerRegistry
from lumi_tool_gateway.mcp.transport import MCPHTTPResponse
from lumi_tool_gateway.registry import ToolRegistry
from lumi_tool_gateway.ssrf import SSRFPolicy
from lumi_tool_gateway.testing import (
    MemoryIdempotentSideEffectGuard,
    StaticApprovalResolver,
)


class Resolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, hostname: str) -> tuple[str, ...]:
        self.calls += 1
        assert hostname == "mcp.example"
        return ("8.8.8.8",)


class Credentials:
    async def credentials_for(self, server, *, organization_id):
        del server
        return MCPRequestAuth(
            organization_id=organization_id,
            headers={"Authorization": "Bearer fixture-token"},
            subject="fixture-user",
        )


class StatelessFixtureTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.tool_calls = 0
        self.instance_index = 0

    async def post(
        self,
        *,
        target,
        headers: dict[str, str],
        body: dict[str, Any],
        timeout_seconds: float,
    ) -> MCPHTTPResponse:
        self.calls.append(
            {
                "target": target,
                "headers": dict(headers),
                "body": body,
                "timeout_seconds": timeout_seconds,
            }
        )
        request_id = body.get("id")
        method = body.get("method")
        params = body.get("params")
        assert isinstance(params, dict)
        if method == "server/discover":
            result = {
                "resultType": "complete",
                "supportedVersions": [MCP_PROTOCOL_2026_07_28],
                "capabilities": {"tools": {}},
                "ttlMs": 10_000,
            }
        elif method == "tools/list":
            result = {
                "resultType": "complete",
                "ttlMs": 10_000,
                "tools": [
                    {
                        "name": "search",
                        "description": "Approved read tool",
                        "inputSchema": {
                            "type": "object",
                            "required": ["query"],
                            "properties": {"query": {"type": "string"}},
                            "additionalProperties": False,
                        },
                        "outputSchema": {
                            "type": "object",
                            "required": ["results", "instance"],
                            "properties": {
                                "results": {"type": "array"},
                                "instance": {"type": "string"},
                            },
                            "additionalProperties": False,
                        },
                    },
                    {
                        "name": "publish",
                        "description": "Approved external write",
                        "inputSchema": {
                            "type": "object",
                            "required": ["text"],
                            "properties": {"text": {"type": "string"}},
                            "additionalProperties": False,
                        },
                        "outputSchema": {
                            "type": "object",
                            "required": ["published"],
                            "properties": {"published": {"type": "boolean"}},
                            "additionalProperties": False,
                        },
                        "annotations": {"readOnlyHint": True},
                    },
                    {
                        "name": "dangerous_unapproved",
                        "description": "Discovery must not authorize this tool",
                        "inputSchema": {"type": "object"},
                    },
                ],
            }
        elif method == "tools/call":
            self.tool_calls += 1
            name = params.get("name")
            self.instance_index += 1
            if name == "publish":
                result = {
                    "resultType": "complete",
                    "structuredContent": {"published": True},
                    "content": [{"type": "text", "text": "published"}],
                    "isError": False,
                }
            else:
                result = {
                    "resultType": "complete",
                    "structuredContent": {
                        "results": ["alpha", "beta"],
                        "instance": f"fixture-{self.instance_index}",
                    },
                    "content": [{"type": "text", "text": "2 results"}],
                    "isError": False,
                }
        else:
            raise AssertionError(f"unexpected method: {method}")
        return MCPHTTPResponse(
            status=200,
            headers={},
            json_body={"jsonrpc": "2.0", "id": request_id, "result": result},
        )


def request(definition, organization_id, *, arguments, idempotency_key=None):
    return ToolRequest(
        tool_call_id=uuid4(),
        organization_id=organization_id,
        agent_run_id=uuid4(),
        task_id=uuid4(),
        actor_agent="mcp-integration-agent",
        name=definition.name,
        version=definition.version,
        arguments=arguments,
        purpose=f"NODE-26 integration {definition.name}",
        permission_context=ToolPermissionContext(
            organization_id=organization_id,
            actor_id="integration-user",
            granted_permissions=definition.permissions,
            agent_allow_patterns=(definition.name,),
        ),
        idempotency_key=idempotency_key,
        trace_id="node26-integration",
    )


async def main_async() -> None:
    organization_id = uuid4()
    resolver = Resolver()
    server = MCPServerDefinition(
        server_id="design",
        name="Design MCP",
        base_url="https://mcp.example/mcp",
        transport=MCPTransportKind.STREAMABLE_HTTP,
        enabled=True,
        approved=True,
        trust_level=MCPTrustLevel.ORGANIZATION_APPROVED,
        organization_id=organization_id,
        allowed_tool_patterns=("*",),
        protocol_versions=(MCP_PROTOCOL_2026_07_28,),
        auth_profile="fixture",
        discovery_ttl_seconds=60,
    )
    registry = MCPServerRegistry(
        (server,),
        ssrf_policy=SSRFPolicy(resolver=resolver),
    )
    transport = StatelessFixtureTransport()
    client = MCPClient(
        registry=registry,
        transport=transport,
        credentials=Credentials(),
    )
    policies = (
        MCPToolPolicy(
            server_id="design",
            remote_tool_name="search",
            risk=ToolRisk.READ_EXTERNAL,
            permissions=frozenset({"tool.mcp.design.search"}),
            idempotency=ToolIdempotency.NOT_REQUIRED,
        ),
        MCPToolPolicy(
            server_id="design",
            remote_tool_name="publish",
            risk=ToolRisk.WRITE_EXTERNAL,
            permissions=frozenset({"tool.mcp.design.publish"}),
            idempotency=ToolIdempotency.REQUIRED,
        ),
    )
    plan = await MCPIntegrationBuilder(client=client).prepare(
        "design",
        organization_id=organization_id,
        policies=policies,
    )
    assert {item.name for item in plan.definitions} == {
        "mcp.design.search",
        "mcp.design.publish",
    }
    assert all("dangerous_unapproved" not in key for key in plan.adapters)

    guard = MemoryIdempotentSideEffectGuard()
    audit = MemoryAuditSink()
    gateway = ToolGateway(
        registry=ToolRegistry(plan.definitions),
        adapters=plan.adapters,
        side_effect_guard=guard,
        audit_sink=audit,
    )
    search = next(item for item in plan.definitions if item.name.endswith("search"))
    first_read = await gateway.invoke(
        request(search, organization_id, arguments={"query": "design"})
    )
    second_read = await gateway.invoke(
        request(search, organization_id, arguments={"query": "systems"})
    )
    assert first_read.status == ToolCallStatus.SUCCEEDED
    assert second_read.status == ToolCallStatus.SUCCEEDED
    assert first_read.data["instance"] != second_read.data["instance"]

    publish = next(item for item in plan.definitions if item.name.endswith("publish"))
    pending = await gateway.invoke(
        request(
            publish,
            organization_id,
            arguments={"text": "hello"},
            idempotency_key="publish-1",
        )
    )
    assert pending.status == ToolCallStatus.APPROVAL_REQUIRED
    calls_before_approval = transport.tool_calls

    approved_gateway = ToolGateway(
        registry=ToolRegistry(plan.definitions),
        adapters=plan.adapters,
        side_effect_guard=guard,
        approval_resolver=StaticApprovalResolver(ApprovalDecision.APPROVED),
        audit_sink=audit,
    )
    publish_request = request(
        publish,
        organization_id,
        arguments={"text": "hello"},
        idempotency_key="publish-1",
    )
    first_write = await approved_gateway.invoke(publish_request)
    replay = await approved_gateway.invoke(publish_request)
    assert first_write.replayed is False
    assert replay.replayed is True
    assert transport.tool_calls == calls_before_approval + 1
    assert guard.invocations == 1
    assert guard.replays == 1

    modern_calls = [
        call for call in transport.calls if call["body"].get("method") != "server/discover"
    ]
    assert all("Mcp-Session-Id" not in call["headers"] for call in modern_calls)
    assert all(call["target"].pinned_ip == "8.8.8.8" for call in transport.calls)
    assert resolver.calls >= len(transport.calls) + 1
    assert all("fixture-token" not in repr(record) for record in audit.records)
    print(
        "NODE-26 MCP Integration: PASS "
        f"tools={len(plan.definitions)} calls={transport.tool_calls} "
        f"audit={len(audit.records)} replays={guard.replays}"
    )


def main() -> int:
    asyncio.run(main_async())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

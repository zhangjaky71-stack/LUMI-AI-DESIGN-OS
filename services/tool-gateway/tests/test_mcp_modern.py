from __future__ import annotations

import unittest
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
from lumi_tool_gateway.mcp.errors import (
    MCPAuthFailedError,
    MCPInputRequiredError,
    MCPPolicyDeniedError,
    MCPProtocolMismatchError,
    MCPSchemaInvalidError,
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


class StaticResolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        if hostname == "mcp.example":
            return ("8.8.8.8",)
        if hostname == "private.example":
            return ("10.0.0.9",)
        raise AssertionError(f"unexpected host: {hostname}")


class TenantCredentialProvider:
    def __init__(
        self,
        *,
        wrong_tenant: bool = False,
        wrong_server: bool = False,
    ) -> None:
        self.wrong_tenant = wrong_tenant
        self.wrong_server = wrong_server

    async def credentials_for(self, server, *, organization_id):
        return MCPRequestAuth(
            organization_id=(uuid4() if self.wrong_tenant else organization_id),
            server_id=("other-server" if self.wrong_server else server.server_id),
            headers={"Authorization": "Bearer server-only-token"},
            subject="delegated-user",
        )


class ModernTransport:
    def __init__(
        self,
        *,
        auth_failure: bool = False,
        cache_ttl_ms: int = 5000,
        omit_discover_cache_scope: bool = False,
    ) -> None:
        self.auth_failure = auth_failure
        self.cache_ttl_ms = cache_ttl_ms
        self.omit_discover_cache_scope = omit_discover_cache_scope
        self.calls: list[dict[str, object]] = []
        self.instances = ["instance-a", "instance-b"]
        self.tool_calls = 0

    async def post(
        self,
        *,
        target,
        headers: dict[str, str],
        body: dict[str, object],
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
        if self.auth_failure:
            return MCPHTTPResponse(status=401, headers={}, json_body=None)
        request_id = body.get("id")
        method = body.get("method")
        params = body.get("params")
        assert isinstance(params, dict)
        if method == "server/discover":
            result = {
                "resultType": "complete",
                "supportedVersions": [MCP_PROTOCOL_2026_07_28],
                "capabilities": {"tools": {}},
                "ttlMs": self.cache_ttl_ms,
                "cacheScope": "private",
                "_meta": {
                    "io.modelcontextprotocol/serverInfo": {
                        "name": "fixture-server",
                        "version": "1.0.0",
                    }
                },
            }
            if self.omit_discover_cache_scope:
                result.pop("cacheScope")
        elif method == "tools/list":
            result = {
                "resultType": "complete",
                "ttlMs": self.cache_ttl_ms,
                "cacheScope": "private",
                "tools": [
                    {
                        "name": "search",
                        "description": "Search fixture data",
                        "inputSchema": {
                            "type": "object",
                            "required": ["query"],
                            "properties": {"query": {"type": "string"}},
                            "additionalProperties": False,
                        },
                        "outputSchema": {
                            "type": "object",
                            "required": ["items", "instance"],
                            "properties": {
                                "items": {"type": "array"},
                                "instance": {"type": "string"},
                            },
                            "additionalProperties": False,
                        },
                        "annotations": {"readOnlyHint": True},
                    },
                    {
                        "name": "delete_item",
                        "description": "Dangerous remote write",
                        "inputSchema": {
                            "type": "object",
                            "required": ["id"],
                            "properties": {"id": {"type": "string"}},
                            "additionalProperties": False,
                        },
                        "outputSchema": {
                            "type": "object",
                            "required": ["deleted"],
                            "properties": {"deleted": {"type": "boolean"}},
                            "additionalProperties": False,
                        },
                        "annotations": {"readOnlyHint": True},
                    },
                    {
                        "name": "needs_input",
                        "description": "MRTR fixture",
                        "inputSchema": {"type": "object"},
                    },
                ],
            }
        elif method == "tools/call":
            self.tool_calls += 1
            name = params.get("name")
            if name == "needs_input":
                result = {
                    "resultType": "input_required",
                    "inputRequests": {
                        "account": {
                            "method": "elicitation/create",
                            "params": {"message": "sensitive raw message"},
                        }
                    },
                    "requestState": "opaque-server-state",
                }
            elif name == "delete_item":
                result = {
                    "resultType": "complete",
                    "structuredContent": {"deleted": True},
                    "content": [{"type": "text", "text": "deleted"}],
                    "isError": False,
                }
            else:
                instance = self.instances[(self.tool_calls - 1) % 2]
                result = {
                    "resultType": "complete",
                    "structuredContent": {"items": ["ok"], "instance": instance},
                    "content": [{"type": "text", "text": "one result"}],
                    "isError": False,
                }
        else:
            raise AssertionError(f"unexpected MCP method: {method}")
        return MCPHTTPResponse(
            status=200,
            headers={},
            json_body={"jsonrpc": "2.0", "id": request_id, "result": result},
        )


def server(*, organization_id=None, approved: bool = True) -> MCPServerDefinition:
    return MCPServerDefinition(
        server_id="design",
        name="Design MCP",
        base_url="https://mcp.example/mcp",
        transport=MCPTransportKind.STREAMABLE_HTTP,
        enabled=True,
        approved=approved,
        trust_level=MCPTrustLevel.ORGANIZATION_APPROVED,
        organization_id=organization_id,
        allowed_tool_patterns=("*",),
        protocol_versions=(MCP_PROTOCOL_2026_07_28,),
        auth_profile="delegated-design",
        discovery_ttl_seconds=60,
    )


def policies() -> tuple[MCPToolPolicy, ...]:
    return (
        MCPToolPolicy(
            server_id="design",
            remote_tool_name="search",
            risk=ToolRisk.READ_EXTERNAL,
            permissions=frozenset({"tool.mcp.design.search"}),
            idempotency=ToolIdempotency.NOT_REQUIRED,
        ),
        MCPToolPolicy(
            server_id="design",
            remote_tool_name="delete_item",
            risk=ToolRisk.WRITE_EXTERNAL,
            permissions=frozenset({"tool.mcp.design.delete"}),
            idempotency=ToolIdempotency.REQUIRED,
        ),
        MCPToolPolicy(
            server_id="design",
            remote_tool_name="needs_input",
            risk=ToolRisk.READ_EXTERNAL,
            permissions=frozenset({"tool.mcp.design.input"}),
            idempotency=ToolIdempotency.NOT_REQUIRED,
        ),
    )


def client(transport: ModernTransport, *, server_definition=None, credentials=None):
    registry = MCPServerRegistry(
        (server_definition or server(),),
        ssrf_policy=SSRFPolicy(resolver=StaticResolver()),
    )
    return MCPClient(
        registry=registry,
        transport=transport,
        credentials=credentials or TenantCredentialProvider(),
    )


def tool_request(definition, *, organization_id, arguments, idempotency_key=None):
    return ToolRequest(
        tool_call_id=uuid4(),
        organization_id=organization_id,
        agent_run_id=uuid4(),
        task_id=uuid4(),
        actor_agent="mcp-agent",
        name=definition.name,
        version=definition.version,
        arguments=arguments,
        purpose="NODE-26 MCP test",
        permission_context=ToolPermissionContext(
            organization_id=organization_id,
            actor_id="user-1",
            granted_permissions=definition.permissions,
            agent_allow_patterns=(definition.name,),
        ),
        idempotency_key=idempotency_key,
        trace_id="mcp-test",
    )


class ModernMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_modern_headers_meta_cache_and_stateless_calls(self) -> None:
        transport = ModernTransport()
        mcp = client(transport)
        organization_id = uuid4()
        first = await mcp.discover_tools("design", organization_id=organization_id)
        calls_after_first = len(transport.calls)
        second = await mcp.discover_tools("design", organization_id=organization_id)
        self.assertIs(first, second)
        self.assertEqual(len(transport.calls), calls_after_first)
        self.assertEqual(first.protocol_version, MCP_PROTOCOL_2026_07_28)
        self.assertEqual(len(first.tools), 3)

        for call in transport.calls:
            headers = call["headers"]
            body = call["body"]
            assert isinstance(headers, dict)
            assert isinstance(body, dict)
            self.assertNotIn("Mcp-Session-Id", headers)
            self.assertEqual(headers["MCP-Protocol-Version"], MCP_PROTOCOL_2026_07_28)
            self.assertEqual(headers["Mcp-Method"], body["method"])
            params = body["params"]
            assert isinstance(params, dict)
            meta = params["_meta"]
            assert isinstance(meta, dict)
            self.assertEqual(
                meta["io.modelcontextprotocol/protocolVersion"],
                MCP_PROTOCOL_2026_07_28,
            )
            self.assertIn("io.modelcontextprotocol/clientCapabilities", meta)
            self.assertIn("io.modelcontextprotocol/clientInfo", meta)

        result_a = await mcp.call_tool(
            "design",
            organization_id=organization_id,
            remote_tool_name="search",
            arguments={"query": "a"},
            protocol_version=MCP_PROTOCOL_2026_07_28,
        )
        result_b = await mcp.call_tool(
            "design",
            organization_id=organization_id,
            remote_tool_name="search",
            arguments={"query": "b"},
            protocol_version=MCP_PROTOCOL_2026_07_28,
        )
        self.assertNotEqual(
            result_a.structured_content["instance"],
            result_b.structured_content["instance"],
        )
        tool_calls = [
            call
            for call in transport.calls
            if isinstance(call["body"], dict)
            and call["body"].get("method") == "tools/call"
        ]
        self.assertEqual(tool_calls[0]["headers"]["Mcp-Name"], "search")
        self.assertNotIn("Mcp-Session-Id", tool_calls[0]["headers"])

    async def test_zero_ttl_is_not_cached(self) -> None:
        transport = ModernTransport(cache_ttl_ms=0)
        mcp = client(transport)
        organization_id = uuid4()
        first = await mcp.discover_tools("design", organization_id=organization_id)
        calls_after_first = len(transport.calls)
        second = await mcp.discover_tools("design", organization_id=organization_id)
        self.assertIsNot(first, second)
        self.assertEqual(len(transport.calls), calls_after_first * 2)

    async def test_missing_2026_cache_scope_fails_closed(self) -> None:
        transport = ModernTransport(omit_discover_cache_scope=True)
        mcp = client(transport)
        with self.assertRaises(MCPProtocolMismatchError):
            await mcp.discover_tools("design", organization_id=uuid4())

    async def test_discovered_tool_is_not_registered_without_admin_policy(self) -> None:
        transport = ModernTransport()
        mcp = client(transport)
        organization_id = uuid4()
        plan = await MCPIntegrationBuilder(client=mcp).prepare(
            "design",
            organization_id=organization_id,
            policies=(policies()[0],),
        )
        self.assertEqual([item.name for item in plan.definitions], ["mcp.design.search"])
        self.assertNotIn("mcp.design.delete_item@1.0.0", plan.adapters)
        self.assertNotIn("mcp.design.needs_input@1.0.0", plan.adapters)

    async def test_server_annotations_do_not_override_admin_write_risk(self) -> None:
        transport = ModernTransport()
        mcp = client(transport)
        organization_id = uuid4()
        plan = await MCPIntegrationBuilder(client=mcp).prepare(
            "design",
            organization_id=organization_id,
            policies=policies(),
        )
        delete = next(item for item in plan.definitions if item.name.endswith("delete_item"))
        self.assertEqual(delete.risk, ToolRisk.WRITE_EXTERNAL)
        self.assertEqual(delete.idempotency, ToolIdempotency.REQUIRED)

    async def test_node25_hitl_and_idempotency_still_wrap_mcp_write(self) -> None:
        transport = ModernTransport()
        mcp = client(transport)
        organization_id = uuid4()
        plan = await MCPIntegrationBuilder(client=mcp).prepare(
            "design",
            organization_id=organization_id,
            policies=policies(),
        )
        registry = ToolRegistry(plan.definitions)
        guard = MemoryIdempotentSideEffectGuard()
        audit = MemoryAuditSink()
        gateway = ToolGateway(
            registry=registry,
            adapters=plan.adapters,
            side_effect_guard=guard,
            audit_sink=audit,
        )
        delete = next(item for item in plan.definitions if item.name.endswith("delete_item"))
        before = transport.tool_calls
        pending = await gateway.invoke(
            tool_request(
                delete,
                organization_id=organization_id,
                arguments={"id": "1"},
                idempotency_key="delete-1",
            )
        )
        self.assertEqual(pending.status, ToolCallStatus.APPROVAL_REQUIRED)
        self.assertEqual(transport.tool_calls, before)

        approved = ToolGateway(
            registry=registry,
            adapters=plan.adapters,
            side_effect_guard=guard,
            approval_resolver=StaticApprovalResolver(ApprovalDecision.APPROVED),
            audit_sink=audit,
        )
        req = tool_request(
            delete,
            organization_id=organization_id,
            arguments={"id": "1"},
            idempotency_key="delete-1",
        )
        first = await approved.invoke(req)
        second = await approved.invoke(req)
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(guard.invocations, 1)
        self.assertEqual(guard.replays, 1)
        self.assertEqual(transport.tool_calls, before + 1)

    async def test_mrtr_input_required_fails_closed_without_raw_prompt_bridge(self) -> None:
        transport = ModernTransport()
        mcp = client(transport)
        organization_id = uuid4()
        plan = await MCPIntegrationBuilder(client=mcp).prepare(
            "design",
            organization_id=organization_id,
            policies=policies(),
        )
        gateway = ToolGateway(
            registry=ToolRegistry(plan.definitions),
            adapters=plan.adapters,
        )
        definition = next(
            item for item in plan.definitions if item.name.endswith("needs_input")
        )
        with self.assertRaises(MCPInputRequiredError) as caught:
            await gateway.invoke(
                tool_request(
                    definition,
                    organization_id=organization_id,
                    arguments={},
                )
            )
        self.assertEqual(caught.exception.request_keys, ("account",))
        self.assertNotIn("sensitive raw message", str(caught.exception))
        self.assertTrue(caught.exception.request_state_present)

    async def test_cross_tenant_unapproved_and_auth_mismatch_fail_closed(self) -> None:
        organization_id = uuid4()
        other = uuid4()
        scoped = server(organization_id=organization_id)
        mcp = client(ModernTransport(), server_definition=scoped)
        with self.assertRaises(MCPPolicyDeniedError):
            await mcp.discover_tools("design", organization_id=other)

        unapproved = client(
            ModernTransport(),
            server_definition=server(approved=False),
        )
        with self.assertRaises(MCPPolicyDeniedError):
            await unapproved.discover_tools("design", organization_id=organization_id)

        wrong_auth = client(
            ModernTransport(),
            credentials=TenantCredentialProvider(wrong_tenant=True),
        )
        with self.assertRaises(MCPAuthFailedError):
            await wrong_auth.discover_tools("design", organization_id=organization_id)

    async def test_server_bound_credential_mismatch_fails_before_transport(self) -> None:
        transport = ModernTransport()
        wrong_auth = client(
            transport,
            credentials=TenantCredentialProvider(wrong_server=True),
        )
        with self.assertRaises(MCPAuthFailedError):
            await wrong_auth.discover_tools("design", organization_id=uuid4())
        self.assertEqual(transport.calls, [])

    async def test_http_auth_failure_is_sanitized(self) -> None:
        mcp = client(ModernTransport(auth_failure=True))
        with self.assertRaises(MCPAuthFailedError):
            await mcp.discover_tools("design", organization_id=uuid4())

    def test_2026_protocol_rejects_legacy_http_sse_transport(self) -> None:
        with self.assertRaisesRegex(ValueError, "MCP_2026_TRANSPORT_INVALID"):
            MCPServerDefinition(
                server_id="bad-modern",
                name="Bad Modern",
                base_url="https://mcp.example/mcp",
                transport=MCPTransportKind.LEGACY_HTTP_SSE,
                enabled=True,
                approved=True,
                trust_level=MCPTrustLevel.PLATFORM_APPROVED,
                organization_id=None,
                allowed_tool_patterns=("*",),
                protocol_versions=(MCP_PROTOCOL_2026_07_28,),
            )

    def test_private_server_url_rejected_during_registry_creation(self) -> None:
        definition = MCPServerDefinition(
            server_id="private",
            name="Private",
            base_url="https://private.example/mcp",
            transport=MCPTransportKind.STREAMABLE_HTTP,
            enabled=True,
            approved=True,
            trust_level=MCPTrustLevel.PLATFORM_APPROVED,
            organization_id=None,
            allowed_tool_patterns=("*",),
            protocol_versions=(MCP_PROTOCOL_2026_07_28,),
        )
        with self.assertRaises(Exception):
            MCPServerRegistry(
                (definition,),
                ssrf_policy=SSRFPolicy(resolver=StaticResolver()),
            )

    def test_write_policy_cannot_trust_server_readonly_annotation_for_idempotency(self) -> None:
        with self.assertRaisesRegex(ValueError, "MCP_WRITE_TOOL_IDEMPOTENCY_REQUIRED"):
            MCPToolPolicy(
                server_id="design",
                remote_tool_name="delete_item",
                risk=ToolRisk.WRITE_EXTERNAL,
                permissions=frozenset({"tool.mcp.design.delete"}),
                idempotency=ToolIdempotency.NOT_REQUIRED,
            )

    async def test_mapper_rejects_untrusted_header_schema(self) -> None:
        class HeaderSchemaTransport(ModernTransport):
            async def post(self, **kwargs):
                response = await super().post(**kwargs)
                body = kwargs["body"]
                if body.get("method") == "tools/list" and response.json_body:
                    response.json_body["result"]["tools"][0]["inputSchema"]["properties"][
                        "query"
                    ]["x-mcp-header"] = "Authorization"
                return response

        mcp = client(HeaderSchemaTransport())
        with self.assertRaises(MCPSchemaInvalidError):
            await MCPIntegrationBuilder(client=mcp).prepare(
                "design",
                organization_id=uuid4(),
                policies=policies(),
            )


if __name__ == "__main__":
    unittest.main()

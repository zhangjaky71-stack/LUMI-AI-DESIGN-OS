from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_tool_gateway.mcp.client import MCPClient
from lumi_tool_gateway.mcp.contracts import (
    MCP_PROTOCOL_2025_11_25,
    MCPServerDefinition,
    MCPTransportKind,
    MCPTrustLevel,
)
from lumi_tool_gateway.mcp.registry import MCPServerRegistry
from lumi_tool_gateway.mcp.transport import MCPHTTPResponse
from lumi_tool_gateway.ssrf import SSRFPolicy


class Resolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        assert hostname == "legacy.example"
        return ("8.8.4.4",)


class LegacyTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.initialize_count = 0

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
        method = body.get("method")
        request_id = body.get("id")
        if method == "initialize":
            self.initialize_count += 1
            return MCPHTTPResponse(
                status=200,
                headers={"Mcp-Session-Id": "legacy-session-1"},
                json_body={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": MCP_PROTOCOL_2025_11_25,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "legacy", "version": "1"},
                    },
                },
            )
        if method == "notifications/initialized":
            self.assert_session(headers)
            return MCPHTTPResponse(status=202, headers={}, json_body=None)
        if method == "tools/list":
            self.assert_session(headers)
            return MCPHTTPResponse(
                status=200,
                headers={},
                json_body={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": "legacy_search",
                                "description": "legacy fixture",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"q": {"type": "string"}},
                                },
                            }
                        ]
                    },
                },
            )
        if method == "tools/call":
            self.assert_session(headers)
            return MCPHTTPResponse(
                status=200,
                headers={},
                json_body={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": "legacy ok"}],
                        "structuredContent": {"ok": True},
                        "isError": False,
                    },
                },
            )
        raise AssertionError(f"unexpected legacy method: {method}")

    @staticmethod
    def assert_session(headers: dict[str, str]) -> None:
        assert headers.get("Mcp-Session-Id") == "legacy-session-1"
        assert headers.get("MCP-Protocol-Version") == MCP_PROTOCOL_2025_11_25


def legacy_server() -> MCPServerDefinition:
    return MCPServerDefinition(
        server_id="legacy",
        name="Legacy MCP",
        base_url="https://legacy.example/mcp",
        transport=MCPTransportKind.LEGACY_HTTP_SSE,
        enabled=True,
        approved=True,
        trust_level=MCPTrustLevel.PLATFORM_APPROVED,
        organization_id=None,
        allowed_tool_patterns=("legacy_*",),
        protocol_versions=(MCP_PROTOCOL_2025_11_25,),
        discovery_ttl_seconds=60,
    )


class LegacyMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_initialize_session_isolated_from_modern_contract(self) -> None:
        transport = LegacyTransport()
        registry = MCPServerRegistry(
            (legacy_server(),),
            ssrf_policy=SSRFPolicy(resolver=Resolver()),
        )
        client = MCPClient(registry=registry, transport=transport)
        organization_id = uuid4()
        discovery = await client.discover_tools(
            "legacy",
            organization_id=organization_id,
        )
        self.assertEqual(discovery.protocol_version, MCP_PROTOCOL_2025_11_25)
        self.assertEqual(discovery.tools[0].remote_name, "legacy_search")
        call = await client.call_tool(
            "legacy",
            organization_id=organization_id,
            remote_tool_name="legacy_search",
            arguments={"q": "hello"},
            protocol_version=MCP_PROTOCOL_2025_11_25,
        )
        self.assertEqual(call.result_type, "complete")
        self.assertEqual(call.structured_content, {"ok": True})
        self.assertEqual(transport.initialize_count, 1)
        methods = [call["body"].get("method") for call in transport.calls]
        self.assertEqual(
            methods,
            ["initialize", "notifications/initialized", "tools/list", "tools/call"],
        )
        modern_headers = [
            call["headers"]
            for call in transport.calls
            if call["body"].get("method") != "initialize"
        ]
        self.assertTrue(all("Mcp-Session-Id" in item for item in modern_headers))


if __name__ == "__main__":
    unittest.main()

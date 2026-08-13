from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_tool_gateway.mcp.client import MCPClient
from lumi_tool_gateway.mcp.contracts import (
    MCP_PROTOCOL_2026_07_28,
    MCPServerDefinition,
    MCPTransportKind,
    MCPTrustLevel,
)
from lumi_tool_gateway.mcp.errors import MCPError
from lumi_tool_gateway.mcp.registry import MCPServerRegistry
from lumi_tool_gateway.mcp.transport import MCPHTTPResponse
from lumi_tool_gateway.ssrf import SSRFPolicy


class Resolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        assert hostname == "mcp.example"
        return ("8.8.8.8",)


class ErrorTransport:
    async def post(
        self,
        *,
        target,
        headers: dict[str, str],
        body: dict[str, object],
        timeout_seconds: float,
    ) -> MCPHTTPResponse:
        del target, headers, timeout_seconds
        return MCPHTTPResponse(
            status=200,
            headers={},
            json_body={
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32099,
                    "message": "raw provider secret token=top-secret",
                    "data": {"credential": "top-secret"},
                },
            },
        )


class MCPErrorSanitizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_raw_jsonrpc_error_message_and_data_do_not_escape(self) -> None:
        server = MCPServerDefinition(
            server_id="design",
            name="Design MCP",
            base_url="https://mcp.example/mcp",
            transport=MCPTransportKind.STREAMABLE_HTTP,
            enabled=True,
            approved=True,
            trust_level=MCPTrustLevel.PLATFORM_APPROVED,
            organization_id=None,
            allowed_tool_patterns=("*",),
            protocol_versions=(MCP_PROTOCOL_2026_07_28,),
        )
        client = MCPClient(
            registry=MCPServerRegistry(
                (server,),
                ssrf_policy=SSRFPolicy(resolver=Resolver()),
            ),
            transport=ErrorTransport(),
        )
        with self.assertRaises(MCPError) as caught:
            await client.discover_tools("design", organization_id=uuid4())
        self.assertNotIn("top-secret", str(caught.exception))
        self.assertNotIn("credential", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

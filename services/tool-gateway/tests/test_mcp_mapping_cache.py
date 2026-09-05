from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_tool_gateway.contracts import ToolIdempotency, ToolRisk
from lumi_tool_gateway.mcp.cache import MCPDiscoveryCache
from lumi_tool_gateway.mcp.contracts import (
    MCP_PROTOCOL_2026_07_28,
    MCPDiscoveredTool,
    MCPDiscoveryResult,
    MCPServerDefinition,
    MCPToolPolicy,
    MCPTransportKind,
    MCPTrustLevel,
)
from lumi_tool_gateway.mcp.errors import MCPPolicyDeniedError, MCPSchemaInvalidError
from lumi_tool_gateway.mcp.mapping import MCPToolMapper


class ManualClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def server() -> MCPServerDefinition:
    return MCPServerDefinition(
        server_id="design",
        name="Design MCP",
        base_url="https://example.com/mcp",
        transport=MCPTransportKind.STREAMABLE_HTTP,
        enabled=True,
        approved=True,
        trust_level=MCPTrustLevel.PLATFORM_APPROVED,
        organization_id=None,
        allowed_tool_patterns=("*",),
        protocol_versions=(MCP_PROTOCOL_2026_07_28,),
    )


def policy(remote_name: str) -> MCPToolPolicy:
    return MCPToolPolicy(
        server_id="design",
        remote_tool_name=remote_name,
        risk=ToolRisk.READ_EXTERNAL,
        permissions=frozenset({f"tool.mcp.design.{remote_name.lower()}"}),
        idempotency=ToolIdempotency.NOT_REQUIRED,
    )


class MCPMappingCacheTests(unittest.TestCase):
    def test_discovery_cache_expires_and_remains_org_scoped(self) -> None:
        clock = ManualClock()
        cache = MCPDiscoveryCache(clock=clock)
        org_a = uuid4()
        org_b = uuid4()
        result = MCPDiscoveryResult(
            protocol_version=MCP_PROTOCOL_2026_07_28,
            tools=(),
            ttl_seconds=5,
        )
        cache.put("design", organization_id=org_a, result=result, ttl_seconds=5)
        self.assertIs(cache.get("design", organization_id=org_a), result)
        self.assertIsNone(cache.get("design", organization_id=org_b))
        clock.advance(5)
        self.assertIsNone(cache.get("design", organization_id=org_a))

    def test_namespacing_collision_is_rejected(self) -> None:
        tools = (
            MCPDiscoveredTool(
                remote_name="Get.User",
                description="one",
                input_schema={"type": "object"},
            ),
            MCPDiscoveredTool(
                remote_name="get.user",
                description="two",
                input_schema={"type": "object"},
            ),
        )
        with self.assertRaises(MCPPolicyDeniedError):
            MCPToolMapper().map_approved_tools(
                server=server(),
                discovered=tools,
                policies=(policy("Get.User"), policy("get.user")),
            )

    def test_unsupported_schema_semantics_are_rejected(self) -> None:
        tool = MCPDiscoveredTool(
            remote_name="search",
            description="fixture",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "pattern": "^safe$",
                    }
                },
            },
        )
        with self.assertRaises(MCPSchemaInvalidError):
            MCPToolMapper().map_tool(
                server=server(),
                tool=tool,
                policy=policy("search"),
            )

    def test_malicious_remote_tool_name_is_rejected_before_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "MCP_TOOL_NAME_INVALID"):
            MCPDiscoveredTool(
                remote_name="../../evil",
                description="bad",
                input_schema={"type": "object"},
            )


if __name__ == "__main__":
    unittest.main()

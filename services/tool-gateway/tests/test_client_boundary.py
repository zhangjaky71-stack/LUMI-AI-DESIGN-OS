from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_tool_gateway.api import ToolGatewayAPI
from lumi_tool_gateway.client import ToolGatewayClient
from lumi_tool_gateway.contracts import (
    ToolAdapterOutput,
    ToolPermissionContext,
    ToolRequest,
)
from lumi_tool_gateway.gateway import ToolGateway
from lumi_tool_gateway.registry import ToolRegistry
from lumi_tool_gateway.testing import CountingAdapter
from lumi_tool_gateway.catalog import p0_tool_definitions


class ToolClientBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_invokes_without_exposing_server_registry_or_adapters(self) -> None:
        definition = next(
            item for item in p0_tool_definitions() if item.name == "project.query"
        )
        adapter = CountingAdapter(ToolAdapterOutput(data={"rows": []}))
        gateway = ToolGateway(
            registry=ToolRegistry((definition,)),
            adapters={definition.key: adapter},
        )
        client = ToolGatewayClient(ToolGatewayAPI(gateway))
        organization_id = uuid4()
        request = ToolRequest(
            tool_call_id=uuid4(),
            organization_id=organization_id,
            agent_run_id=uuid4(),
            task_id=uuid4(),
            actor_agent="planner",
            name=definition.name,
            version=definition.version,
            arguments={"query": "project.summary", "parameters": {}},
            purpose="read project summary",
            permission_context=ToolPermissionContext(
                organization_id=organization_id,
                actor_id="user-1",
                granted_permissions=definition.permissions,
                agent_allow_patterns=(definition.name,),
            ),
        )
        result = await client.invoke(request)
        self.assertEqual(result.data, {"rows": []})
        self.assertEqual(adapter.calls, 1)
        self.assertFalse(hasattr(client, "registry"))
        self.assertFalse(hasattr(client, "adapters"))
        self.assertFalse(hasattr(client, "side_effect_guard"))


if __name__ == "__main__":
    unittest.main()

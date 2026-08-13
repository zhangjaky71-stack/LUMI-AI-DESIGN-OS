from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from lumi_agent_runtime.deep_runtime.contracts import DeepAgentInvocationContext
from lumi_agent_runtime.deep_runtime.tooling import (
    BoundToolDefinition,
    LumiToolGatewayProvider,
)


class Reader:
    async def resolve(self, name: str) -> BoundToolDefinition:
        return BoundToolDefinition(
            name=name,
            version="1.0.0",
            description="Trusted tool description",
            input_schema={"type": "object", "additionalProperties": True},
        )


class Gateway:
    def __init__(self) -> None:
        self.calls = []

    async def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


class FakeStructuredTool:
    @classmethod
    def from_function(cls, *, coroutine, name, description):
        instance = cls()
        instance.coroutine = coroutine
        instance.name = name
        instance.description = description
        return instance


class DeepRuntimeToolingTests(unittest.IsolatedAsyncioTestCase):
    async def test_framework_tool_call_id_becomes_stable_idempotency_key(self) -> None:
        gateway = Gateway()
        provider = LumiToolGatewayProvider(definitions=Reader(), gateway=gateway)
        context = DeepAgentInvocationContext(
            organization_id=uuid4(),
            project_id=uuid4(),
            agent_run_id=uuid4(),
            task_id=uuid4(),
            operation_id=uuid4(),
            actor_id="user-1",
            root_agent="designer",
            granted_permissions=frozenset({"tools:write"}),
            allowed_tools=("asset.write-derived",),
        )
        with patch(
            "lumi_agent_runtime.deep_runtime.tooling._langchain_tool_types",
            return_value=(object(), FakeStructuredTool),
        ):
            tools = await provider.tools_for_root(
                context=context,
                allowed_tools=("asset.write-derived",),
            )
        tool = tools[0]
        first = await tool.coroutine(
            {"source": "asset-1"},
            tool_call_id="call-stable-42",
        )
        second = await tool.coroutine(
            {"source": "asset-1"},
            tool_call_id="call-stable-42",
        )
        self.assertEqual(first, {"ok": True})
        self.assertEqual(second, {"ok": True})
        expected = f"deep-agent:{context.agent_run_id}:call-stable-42"
        self.assertEqual(gateway.calls[0]["idempotency_key"], expected)
        self.assertEqual(gateway.calls[1]["idempotency_key"], expected)
        self.assertTrue(tool._lumi_tool_gateway_bound)
        self.assertEqual(tool._lumi_tool_name, "asset.write-derived")

    async def test_subagent_parent_scope_is_forwarded(self) -> None:
        from lumi_agent_runtime.deep_runtime.contracts import SubagentInvocationContext

        gateway = Gateway()
        provider = LumiToolGatewayProvider(definitions=Reader(), gateway=gateway)
        context = SubagentInvocationContext(
            organization_id=uuid4(),
            project_id=uuid4(),
            agent_run_id=uuid4(),
            task_id=None,
            operation_id=uuid4(),
            actor_id="user-1",
            root_agent="designer",
            subagent_name="researcher",
            depth=1,
            granted_permissions=frozenset({"tools:web.search"}),
            parent_allowed_tools=("web.search", "artifact.query"),
            allowed_tools=("web.search",),
        )
        with patch(
            "lumi_agent_runtime.deep_runtime.tooling._langchain_tool_types",
            return_value=(object(), FakeStructuredTool),
        ):
            tools = await provider.tools_for_subagent(
                context=context,
                allowed_tools=("web.search",),
            )
        await tools[0].coroutine({"query": "LUMI"}, tool_call_id="call-1")
        self.assertEqual(
            gateway.calls[0]["parent_allowed_tools"],
            ("web.search", "artifact.query"),
        )
        self.assertEqual(gateway.calls[0]["actor_agent"], "researcher")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import asyncio
from uuid import uuid4

from lumi_agent_runtime.deep_runtime.contracts import DeepAgentInvocationContext
from lumi_agent_runtime.deep_runtime.node25_adapter import StaticToolDefinitionReader
from lumi_agent_runtime.deep_runtime.tooling import (
    BoundToolDefinition,
    LumiToolGatewayProvider,
)


class CaptureGateway:
    def __init__(self) -> None:
        self.calls = []

    async def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "idempotency_key": kwargs["idempotency_key"]}


async def main_async() -> None:
    canonical = "asset.write-derived"
    reader = StaticToolDefinitionReader(
        (
            BoundToolDefinition(
                name=canonical,
                version="1.0.0",
                description="Create a derived Asset through LUMI Tool Gateway.",
                input_schema={
                    "type": "object",
                    "properties": {"source": {"type": "string"}},
                    "required": ["source"],
                    "additionalProperties": False,
                },
            ),
        )
    )
    gateway = CaptureGateway()
    provider = LumiToolGatewayProvider(definitions=reader, gateway=gateway)
    context = DeepAgentInvocationContext(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        task_id=uuid4(),
        operation_id=uuid4(),
        actor_id="node29-tool-acceptance",
        root_agent="designer",
        granted_permissions=frozenset({"assets:write"}),
        allowed_tools=(canonical,),
    )
    tools = await provider.tools_for_root(context=context, allowed_tools=(canonical,))
    assert len(tools) == 1
    tool = tools[0]
    schema = tool.args_schema.model_json_schema()
    properties = schema.get("properties", {})
    assert "payload" in properties
    assert "tool_call_id" not in properties, schema

    call_id = "node29-framework-call-1"
    result = await tool.ainvoke(
        {
            "name": tool.name,
            "args": {"payload": {"source": "asset-1"}},
            "id": call_id,
            "type": "tool_call",
        }
    )
    assert gateway.calls
    expected = f"deep-agent:{context.agent_run_id}:{call_id}"
    assert gateway.calls[0]["idempotency_key"] == expected
    assert gateway.calls[0]["tool_call_id"] == call_id
    assert result["idempotency_key"] == expected


def main() -> int:
    asyncio.run(main_async())
    print("NODE-29 LangChain injected ToolCall -> NODE-25 idempotency integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

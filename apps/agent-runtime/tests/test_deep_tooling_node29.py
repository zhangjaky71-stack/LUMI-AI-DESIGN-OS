from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from lumi_agent_runtime.deep_runtime.contracts import DeepAgentInvocationContext, PermissionScope
from lumi_agent_runtime.deep_runtime.errors import DeepAgentBudgetExceeded, DeepAgentToolScopeError
from lumi_agent_runtime.deep_runtime.testing import MemoryBudgetMeter, MemoryOffloader
from lumi_agent_runtime.deep_runtime.tooling import BoundToolDefinition, LumiToolGatewayProvider


class Definitions:
    async def resolve(self, name: str) -> BoundToolDefinition:
        return BoundToolDefinition(
            name=name,
            version="1.0.0",
            description="Fixture tool",
            input_schema={"type": "object"},
        )


class Gateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return {"payload": "x" * 500}


class FakeStructuredTool:
    @classmethod
    def from_function(cls, *, coroutine, name, description):
        return SimpleNamespace(coroutine=coroutine, name=name, description=description)


def _context() -> DeepAgentInvocationContext:
    return DeepAgentInvocationContext(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        task_id=uuid4(),
        operation_id=uuid4(),
        actor_id="user:test",
        root_agent="researcher",
        permissions=PermissionScope(allowed_tools=("web.search",)),
        budget_limit_usd="1.00",
    )


def _provider(monkeypatch, *, calls_left: int = 2):
    monkeypatch.setattr(
        "lumi_agent_runtime.deep_runtime.tooling._langchain_tool_types",
        lambda: (object(), FakeStructuredTool),
    )
    gateway = Gateway()
    budget = MemoryBudgetMeter(tool_calls_left=calls_left)
    offloader = MemoryOffloader(threshold=64)
    provider = LumiToolGatewayProvider(
        definitions=Definitions(),
        gateway=gateway,
        budget=budget,
        offloader=offloader,
    )
    return provider, gateway, budget, offloader


def test_tool_scope_is_server_injected_and_large_result_is_offloaded(monkeypatch) -> None:
    provider, gateway, _, offloader = _provider(monkeypatch)
    context = _context()
    tools = asyncio.run(
        provider.tools_for_root(context=context, allowed_tools=("web.search",))
    )
    result = asyncio.run(tools[0].coroutine({"query": "layout"}, "call-1"))
    assert result["ref"].startswith("tool-result://")
    assert offloader.offloaded == 1
    call = gateway.calls[0]
    assert call["context"].organization_id == context.organization_id
    assert call["idempotency_key"].startswith("deep-agent:")

    with pytest.raises(DeepAgentToolScopeError, match="scope injection"):
        asyncio.run(
            tools[0].coroutine(
                {"query": "x", "nested": {"organization_id": str(uuid4())}},
                "call-2",
            )
        )
    assert len(gateway.calls) == 1


def test_tool_call_is_blocked_by_server_budget_before_gateway(monkeypatch) -> None:
    provider, gateway, _, _ = _provider(monkeypatch, calls_left=0)
    tools = asyncio.run(
        provider.tools_for_root(context=_context(), allowed_tools=("web.search",))
    )
    with pytest.raises(DeepAgentBudgetExceeded):
        asyncio.run(tools[0].coroutine({"query": "x"}, "call-1"))
    assert gateway.calls == []

from __future__ import annotations

import asyncio
import inspect
from importlib import import_module
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentDefinition,
    DeepAgentInvocationContext,
    DeepSubagentDefinition,
    DelegationLimits,
)
from lumi_agent_runtime.deep_runtime.providers import mark_backend_bound, mark_model_gateway_bound
from lumi_agent_runtime.deep_runtime.runtime_factory import BoundedDeepAgentRuntimeFactory


class FinalAnswerModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "lumi-node29-final-answer-test-model"

    def bind_tools(self, tools, **kwargs):
        del tools, kwargs
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        del messages, stop, run_manager, kwargs
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(content="NODE29_DEEP_AGENT_OK")
                )
            ]
        )


class Models:
    def __init__(self) -> None:
        self.model = mark_model_gateway_bound(FinalAnswerModel())

    async def model_for_root(self, *, model_profile, context):
        del model_profile, context
        return self.model

    async def model_for_subagent(self, *, definition, context):
        del definition, context
        return self.model


class NoExternalTools:
    async def tools_for_root(self, *, context, allowed_tools):
        del context
        assert allowed_tools == ()
        return ()

    async def tools_for_subagent(self, *, context, allowed_tools):
        del context
        assert allowed_tools == ()
        return ()


class StateBackendProvider:
    async def backend_for_run(self, *, context, virtual_files_enabled):
        del context
        assert virtual_files_enabled is True
        try:
            backend_type = getattr(import_module("deepagents.backends"), "StateBackend")
        except (ImportError, AttributeError) as exc:
            raise AssertionError("current Deep Agents StateBackend is unavailable") from exc

        def backend_factory(runtime):
            parameters = inspect.signature(backend_type).parameters
            if len(parameters) == 0:
                return backend_type()
            return backend_type(runtime)

        return mark_backend_bound(backend_factory)


class Checkpointers:
    def __init__(self) -> None:
        self.checkpointer = InMemorySaver()

    async def checkpointer_for_run(self, *, context):
        del context
        return self.checkpointer


async def main_async() -> None:
    definition = DeepAgentDefinition(
        agent_key="acceptance",
        runtime_version="1.0.0",
        graph_key="deep.acceptance",
        graph_version="1.0.0",
        agent_config_version="agent-v1",
        system_prompt=(
            "You are the NODE-29 acceptance agent. Answer the user directly. "
            "Do not call tools or subagents for this deterministic smoke test."
        ),
        model_profile="node22-test-profile",
        allowed_tools=(),
        subagents=(
            DeepSubagentDefinition(
                name="researcher",
                description="A leaf research subagent used to verify current subagent config.",
                system_prompt="Return a direct answer without tools.",
                allowed_tools=(),
                model_profile="node22-test-profile",
                can_delegate=False,
            ),
        ),
        delegation=DelegationLimits(
            max_depth=1,
            max_total_subagent_calls=2,
            max_parallel_subagents=1,
            max_children_per_agent=2,
        ),
        max_steps=12,
        virtual_files_enabled=True,
    )
    context = DeepAgentInvocationContext(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        task_id=uuid4(),
        operation_id=uuid4(),
        actor_id="node29-acceptance",
        root_agent="acceptance",
        granted_permissions=frozenset({"agent:execute"}),
        allowed_tools=(),
    )
    factory = BoundedDeepAgentRuntimeFactory(
        models=Models(),
        tools=NoExternalTools(),
        backends=StateBackendProvider(),
        checkpointers=Checkpointers(),
    )
    compiled = await factory.compile(definition, context=context)
    assert compiled.compiled_graph.checkpointer is not None
    result = await compiled.compiled_graph.ainvoke(
        {"messages": [HumanMessage(content="Return the acceptance marker.")]},
        config={
            "configurable": {"thread_id": f"node29-{context.agent_run_id}"},
            "recursion_limit": 999,
            "max_concurrency": 999,
        },
    )
    messages = result.get("messages") if isinstance(result, dict) else None
    assert isinstance(messages, list) and messages
    assert isinstance(messages[-1], AIMessage)
    assert messages[-1].content == "NODE29_DEEP_AGENT_OK"


def main() -> int:
    asyncio.run(main_async())
    print("NODE-29 current Deep Agents create_deep_agent integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

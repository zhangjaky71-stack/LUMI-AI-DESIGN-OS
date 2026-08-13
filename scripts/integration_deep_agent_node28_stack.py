from __future__ import annotations

import asyncio
import inspect
from importlib import import_module
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentDefinition,
    DeepAgentInvocationContext,
    DelegationLimits,
)
from lumi_agent_runtime.deep_runtime.control_plane import DeepAgentControlPlaneCompiler
from lumi_agent_runtime.deep_runtime.providers import mark_backend_bound, mark_model_gateway_bound
from lumi_agent_runtime.deep_runtime.registry import DeepAgentRegistry
from lumi_agent_runtime.deep_runtime.runtime_factory import BoundedDeepAgentRuntimeFactory


class Model(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "lumi-node29-stack-model"

    def bind_tools(self, tools, **kwargs):
        del tools, kwargs
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        del messages, stop, run_manager, kwargs
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="stack-ok"))]
        )


class Models:
    def __init__(self) -> None:
        self.model = mark_model_gateway_bound(Model())

    async def model_for_root(self, *, model_profile, context):
        del model_profile, context
        return self.model

    async def model_for_subagent(self, *, definition, context):
        del definition, context
        return self.model


class Tools:
    async def tools_for_root(self, *, context, allowed_tools):
        del context
        assert allowed_tools == ()
        return ()

    async def tools_for_subagent(self, *, context, allowed_tools):
        del context
        assert allowed_tools == ()
        return ()


class Backends:
    async def backend_for_run(self, *, context, virtual_files_enabled):
        del context, virtual_files_enabled
        backend_type = getattr(import_module("deepagents.backends"), "StateBackend")

        def factory(runtime):
            parameters = inspect.signature(backend_type).parameters
            return backend_type() if len(parameters) == 0 else backend_type(runtime)

        return mark_backend_bound(factory)


class Checkpointers:
    async def checkpointer_for_run(self, *, context):
        del context
        return InMemorySaver()


async def main_async() -> None:
    definition = DeepAgentDefinition(
        agent_key="stack",
        runtime_version="1.0.0",
        graph_key="deep.stack",
        graph_version="3.2.1",
        agent_config_version="agent-stack-v2",
        system_prompt="Return a direct answer. Do not call tools or subagents.",
        model_profile="node22-stack-profile",
        allowed_tools=(),
        subagents=(),
        delegation=DelegationLimits(max_depth=1, max_parallel_subagents=1),
        max_steps=10,
    )
    context = DeepAgentInvocationContext(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        task_id=None,
        operation_id=uuid4(),
        actor_id="node29-stack",
        root_agent="stack",
        granted_permissions=frozenset({"agent:execute"}),
        allowed_tools=(),
    )
    compiler = DeepAgentControlPlaneCompiler(
        deep_agents=DeepAgentRegistry((definition,)),
        factory=BoundedDeepAgentRuntimeFactory(
            models=Models(),
            tools=Tools(),
            backends=Backends(),
            checkpointers=Checkpointers(),
        ),
    )
    bundle = await compiler.compile(
        agent_key="stack",
        runtime_version="1.0.0",
        context=context,
    )
    resolved = bundle.graph_registry.resolve(
        definition.graph_key,
        definition.graph_version,
        agent_config_version=definition.agent_config_version,
    )
    assert resolved.metadata["deep_agent_definition_hash"] == definition.content_hash
    exact_definition, exact_graph = bundle.compiled_graph_registry.resolve(
        definition.graph_key,
        definition.graph_version,
        agent_config_version=definition.agent_config_version,
    )
    assert exact_definition.content_hash == resolved.content_hash
    assert exact_graph is bundle.compiled_graph
    assert exact_graph.checkpointer is not None


def main() -> int:
    asyncio.run(main_async())
    print("NODE-29 Deep Agents -> NODE-28 exact-version stack integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

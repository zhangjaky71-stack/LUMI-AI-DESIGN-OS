from __future__ import annotations

from .contracts import DeepAgentDefinition, DeepAgentInvocationContext
from .factory import CompiledDeepAgent, DeepAgentRuntimeFactory
from .graph_limits import LimitedCompiledDeepAgent
from .model_gateway_chat import HttpProfileModelProvider
from .ports import (
    DeepAgentBackendProvider,
    DeepAgentCheckpointerProvider,
    DeepAgentStoreProvider,
    DeepAgentToolProvider,
)


class BoundedDeepAgentRuntimeFactory(DeepAgentRuntimeFactory):
    """NODE-29 bounded factory used by tests and explicit trusted compositions."""

    async def compile(
        self,
        definition: DeepAgentDefinition,
        *,
        context: DeepAgentInvocationContext,
    ) -> CompiledDeepAgent:
        compiled = await super().compile(definition, context=context)
        limited_graph = LimitedCompiledDeepAgent(
            compiled.compiled_graph,
            recursion_limit=definition.max_steps,
            max_concurrency=definition.delegation.max_parallel_subagents,
        )
        return CompiledDeepAgent(
            definition=compiled.definition,
            graph_definition=compiled.graph_definition,
            compiled_graph=limited_graph,
            effective_root_tools=compiled.effective_root_tools,
            subagent_tools=compiled.subagent_tools,
        )


class HostedDeepAgentRuntimeFactory(BoundedDeepAgentRuntimeFactory):
    """Production composition root with a non-injectable private Model Gateway provider."""

    def __init__(
        self,
        *,
        tools: DeepAgentToolProvider,
        backends: DeepAgentBackendProvider,
        checkpointers: DeepAgentCheckpointerProvider,
        stores: DeepAgentStoreProvider | None = None,
    ) -> None:
        super().__init__(
            models=HttpProfileModelProvider.from_env(),
            tools=tools,
            backends=backends,
            checkpointers=checkpointers,
            stores=stores,
        )

from __future__ import annotations

from .contracts import DeepAgentDefinition, DeepAgentInvocationContext
from .factory import CompiledDeepAgent, DeepAgentRuntimeFactory
from .graph_limits import LimitedCompiledDeepAgent


class BoundedDeepAgentRuntimeFactory(DeepAgentRuntimeFactory):
    """Production NODE-29 factory: trusted boundary composition + hard graph limits."""

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

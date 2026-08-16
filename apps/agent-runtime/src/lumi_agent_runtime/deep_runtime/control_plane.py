from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from lumi_agent_runtime.control_plane.contracts import GraphDefinition
from lumi_agent_runtime.control_plane.durable_executor import DurableCompiledGraphRegistry
from lumi_agent_runtime.control_plane.registry import GraphRegistry

from .contracts import DeepAgentDefinition, DeepAgentInvocationContext
from .errors import DeepAgentVersionConflictError
from .registry import DeepAgentRegistry
from .runtime_factory import BoundedDeepAgentRuntimeFactory


class GraphCatalogVerifier(Protocol):
    async def verify(self, definition: GraphDefinition) -> None: ...


@dataclass(frozen=True, slots=True)
class DeepAgentControlPlaneBundle:
    deep_agent: DeepAgentDefinition
    graph_definition: GraphDefinition
    compiled_graph: Any
    graph_registry: GraphRegistry
    compiled_graph_registry: DurableCompiledGraphRegistry


class DeepAgentControlPlaneCompiler:
    """Compile exact Deep Agent versions into NODE-28 durable graph registries."""

    def __init__(
        self,
        *,
        deep_agents: DeepAgentRegistry,
        factory: BoundedDeepAgentRuntimeFactory,
        graph_catalog: GraphCatalogVerifier | None = None,
    ) -> None:
        self.deep_agents = deep_agents
        self.factory = factory
        self.graph_catalog = graph_catalog

    async def compile(
        self,
        *,
        agent_key: str,
        runtime_version: str,
        context: DeepAgentInvocationContext,
    ) -> DeepAgentControlPlaneBundle:
        definition = self.deep_agents.resolve(agent_key, runtime_version)
        if context.root_agent != definition.agent_key:
            raise DeepAgentVersionConflictError("Deep Agent context/definition mismatch")
        compiled = await self.factory.compile(definition, context=context)
        if (
            compiled.graph_definition.graph_key != definition.graph_key
            or compiled.graph_definition.graph_version != definition.graph_version
            or compiled.graph_definition.agent_config_version
            != definition.agent_config_version
            or compiled.graph_definition.metadata.get("deep_agent_definition_hash")
            != definition.content_hash
        ):
            raise DeepAgentVersionConflictError(
                "compiled Deep Agent graph provenance does not match immutable definition"
            )
        if self.graph_catalog is not None:
            await self.graph_catalog.verify(compiled.graph_definition)
        graph_registry = GraphRegistry((compiled.graph_definition,))
        compiled_registry = DurableCompiledGraphRegistry()
        compiled_registry.register(
            compiled.graph_definition,
            compiled.compiled_graph,
        )
        return DeepAgentControlPlaneBundle(
            deep_agent=definition,
            graph_definition=compiled.graph_definition,
            compiled_graph=compiled.compiled_graph,
            graph_registry=graph_registry,
            compiled_graph_registry=compiled_registry,
        )

from __future__ import annotations

import inspect
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from lumi_agent_runtime.control_plane.contracts import GraphDefinition

from .contracts import (
    DeepAgentDefinition,
    DeepAgentInvocationContext,
    SubagentInvocationContext,
)
from .errors import (
    DeepAgentBackendBoundaryError,
    DeepAgentDelegationDeniedError,
    DeepAgentFactoryError,
    DeepAgentModelBoundaryError,
    DeepAgentToolScopeError,
)
from .ports import (
    DeepAgentBackendProvider,
    DeepAgentCheckpointerProvider,
    DeepAgentModelProvider,
    DeepAgentStoreProvider,
    DeepAgentToolProvider,
)


@dataclass(frozen=True, slots=True)
class CompiledDeepAgent:
    definition: DeepAgentDefinition
    graph_definition: GraphDefinition
    compiled_graph: Any
    effective_root_tools: tuple[str, ...]
    subagent_tools: dict[str, tuple[str, ...]]


class DeepAgentRuntimeFactory:
    """Compile current Deep Agents behind LUMI's model/tool/backend/checkpoint ports."""

    def __init__(
        self,
        *,
        models: DeepAgentModelProvider,
        tools: DeepAgentToolProvider,
        backends: DeepAgentBackendProvider,
        checkpointers: DeepAgentCheckpointerProvider,
        stores: DeepAgentStoreProvider | None = None,
    ) -> None:
        self.models = models
        self.tools = tools
        self.backends = backends
        self.checkpointers = checkpointers
        self.stores = stores

    async def compile(
        self,
        definition: DeepAgentDefinition,
        *,
        context: DeepAgentInvocationContext,
    ) -> CompiledDeepAgent:
        self._validate_context(definition, context)
        if any(child.can_delegate for child in definition.subagents):
            raise DeepAgentDelegationDeniedError(
                "NODE-29 P0 forbids nested subagent delegation; use root->leaf delegation only"
            )

        effective_root_tools = _ordered_intersection(
            definition.allowed_tools,
            context.allowed_tools,
        )
        root_model = await self.models.model_for_root(
            model_profile=definition.model_profile,
            context=context,
        )
        _assert_gateway_model(root_model, profile=definition.model_profile)
        root_tools = await self.tools.tools_for_root(
            context=context,
            allowed_tools=effective_root_tools,
        )
        _assert_gateway_tools(root_tools, expected=effective_root_tools)
        backend = await self.backends.backend_for_run(
            context=context,
            virtual_files_enabled=definition.virtual_files_enabled,
        )
        _assert_backend(backend)
        checkpointer = await self.checkpointers.checkpointer_for_run(context=context)
        if checkpointer is None:
            raise DeepAgentFactoryError("durable Deep Agent requires a NODE-28 checkpointer")
        store = (
            await self.stores.store_for_run(context=context)
            if self.stores is not None
            else None
        )

        subagent_configs: list[dict[str, Any]] = []
        subagent_tools: dict[str, tuple[str, ...]] = {}
        for child in definition.subagents:
            child_allowed = _ordered_intersection(
                child.allowed_tools,
                effective_root_tools,
            )
            child_context = SubagentInvocationContext(
                organization_id=context.organization_id,
                project_id=context.project_id,
                agent_run_id=context.agent_run_id,
                task_id=context.task_id,
                operation_id=context.operation_id,
                actor_id=context.actor_id,
                root_agent=context.root_agent,
                subagent_name=child.name,
                depth=1,
                granted_permissions=context.granted_permissions,
                parent_allowed_tools=effective_root_tools,
                allowed_tools=child_allowed,
                trace_id=context.trace_id,
                budget_limit_usd=context.budget_limit_usd,
            )
            child_model = await self.models.model_for_subagent(
                definition=child,
                context=child_context,
            )
            _assert_gateway_model(child_model, profile=child.model_profile)
            child_tools = await self.tools.tools_for_subagent(
                context=child_context,
                allowed_tools=child_allowed,
            )
            _assert_gateway_tools(child_tools, expected=child_allowed)
            subagent_tools[child.name] = child_allowed
            subagent_configs.append(
                {
                    "name": child.name,
                    "description": child.description,
                    "system_prompt": child.system_prompt,
                    "model": child_model,
                    "tools": list(child_tools),
                }
            )

        create_deep_agent = _load_create_deep_agent()
        _require_current_factory_contract(create_deep_agent)
        kwargs: dict[str, Any] = {
            "model": root_model,
            "tools": list(root_tools),
            "system_prompt": definition.system_prompt,
            "subagents": subagent_configs,
            "backend": backend,
            "checkpointer": checkpointer,
        }
        parameters = inspect.signature(create_deep_agent).parameters
        if "name" in parameters:
            kwargs["name"] = definition.agent_key
        if store is not None:
            if "store" not in parameters:
                raise DeepAgentFactoryError(
                    "installed Deep Agents does not support the required store parameter"
                )
            kwargs["store"] = store
        try:
            compiled = create_deep_agent(**kwargs)
        except Exception as exc:
            raise DeepAgentFactoryError("Deep Agents factory compilation failed") from exc
        if getattr(compiled, "checkpointer", None) is None:
            raise DeepAgentFactoryError("compiled Deep Agent lost the durable checkpointer")

        graph_definition = GraphDefinition(
            graph_key=definition.graph_key,
            graph_version=definition.graph_version,
            agent_config_version=definition.agent_config_version,
            description=f"Deep Agent runtime {definition.identity}",
            state_schema_version=1,
            interrupt_policy_version="deep-runtime-v1",
            metadata={
                "deep_agent_key": definition.agent_key,
                "deep_agent_runtime_version": definition.runtime_version,
                "deep_agent_definition_hash": definition.content_hash,
                "model_profile": definition.model_profile,
                "root_tools": list(effective_root_tools),
                "subagents": [child.name for child in definition.subagents],
                "recursion_limit": definition.max_steps,
                "planning_enabled": definition.planning_enabled,
                "virtual_files_enabled": definition.virtual_files_enabled,
                "delegation_max_depth": definition.delegation.max_depth,
                "delegation_max_total_calls": definition.delegation.max_total_subagent_calls,
            },
        )
        return CompiledDeepAgent(
            definition=definition,
            graph_definition=graph_definition,
            compiled_graph=compiled,
            effective_root_tools=effective_root_tools,
            subagent_tools=subagent_tools,
        )

    def _validate_context(
        self,
        definition: DeepAgentDefinition,
        context: DeepAgentInvocationContext,
    ) -> None:
        if context.root_agent != definition.agent_key:
            raise DeepAgentToolScopeError("runtime context root agent differs from definition")
        requested = set(context.allowed_tools)
        declared = set(definition.allowed_tools)
        if not requested <= declared:
            extra = ",".join(sorted(requested - declared))
            raise DeepAgentToolScopeError(f"runtime context expands tool scope: {extra}")


def _ordered_intersection(
    declared: tuple[str, ...],
    allowed: tuple[str, ...],
) -> tuple[str, ...]:
    allowed_set = set(allowed)
    return tuple(item for item in declared if item in allowed_set)


def _load_create_deep_agent():
    try:
        module = import_module("deepagents")
        factory = getattr(module, "create_deep_agent")
    except (ImportError, AttributeError) as exc:
        raise DeepAgentFactoryError(
            "current deepagents package with create_deep_agent is required"
        ) from exc
    return factory


def _require_current_factory_contract(factory: Any) -> None:
    try:
        parameters = inspect.signature(factory).parameters
    except (TypeError, ValueError) as exc:
        raise DeepAgentFactoryError("cannot inspect create_deep_agent signature") from exc
    required = {"model", "tools", "system_prompt", "subagents", "backend", "checkpointer"}
    missing = required - set(parameters)
    if missing:
        raise DeepAgentFactoryError(
            "installed Deep Agents factory is missing required capabilities: "
            + ",".join(sorted(missing))
        )


def _assert_gateway_model(model: Any, *, profile: str) -> None:
    if not bool(getattr(model, "_lumi_model_gateway_bound", False)):
        raise DeepAgentModelBoundaryError(
            f"model profile {profile} is not bound to NODE-22 Model Gateway"
        )


def _assert_gateway_tools(tools: tuple[Any, ...], *, expected: tuple[str, ...]) -> None:
    seen: list[str] = []
    for tool in tools:
        if not bool(getattr(tool, "_lumi_tool_gateway_bound", False)):
            raise DeepAgentToolScopeError("Deep Agent tool bypasses NODE-25 Tool Gateway")
        canonical = getattr(tool, "_lumi_tool_name", None)
        if not isinstance(canonical, str):
            raise DeepAgentToolScopeError("Tool Gateway wrapper has no canonical tool name")
        seen.append(canonical)
    if tuple(seen) != expected:
        raise DeepAgentToolScopeError(
            f"Tool Gateway provider returned unexpected tool scope: {seen!r} != {expected!r}"
        )


def _assert_backend(backend: Any) -> None:
    if not bool(getattr(backend, "_lumi_backend_bound", False)):
        raise DeepAgentBackendBoundaryError(
            "Deep Agents backend must be provided by a LUMI trusted backend adapter"
        )
    identity = f"{type(backend).__module__}.{type(backend).__name__}".lower()
    for marker in ("filesystembackend", "localshell", "local_shell", "dockerbackend"):
        if marker in identity:
            raise DeepAgentBackendBoundaryError(
                f"host-local Deep Agents backend is forbidden: {identity}"
            )
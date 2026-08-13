from __future__ import annotations

import inspect
from typing import Any

from lumi_agent_runtime.control_plane.contracts import GraphDefinition
from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentDefinition,
    DeepAgentInvocationContext,
    SubagentInvocationContext,
)
from lumi_agent_runtime.deep_runtime.errors import (
    DeepAgentDelegationDeniedError,
    DeepAgentFactoryError,
)
from lumi_agent_runtime.deep_runtime.factory import (
    CompiledDeepAgent,
    _assert_backend,
    _assert_gateway_model,
    _assert_gateway_tools,
    _load_create_deep_agent,
    _ordered_intersection,
    _require_current_factory_contract,
)
from lumi_agent_runtime.deep_runtime.graph_limits import LimitedCompiledDeepAgent
from lumi_agent_runtime.deep_runtime.runtime_factory import BoundedDeepAgentRuntimeFactory

from .deep_bundle import DeepAgentsSkillBundle


class SkillAwareDeepAgentCompiler:
    """Compile a NODE-29 Deep Agent with one exact NODE-31 Skill pack."""

    def __init__(self, base_factory: BoundedDeepAgentRuntimeFactory) -> None:
        self.base_factory = base_factory

    async def compile(
        self,
        definition: DeepAgentDefinition,
        *,
        context: DeepAgentInvocationContext,
        bundle: DeepAgentsSkillBundle,
    ) -> CompiledDeepAgent:
        self.base_factory._validate_context(definition, context)
        if any(child.can_delegate for child in definition.subagents):
            raise DeepAgentDelegationDeniedError(
                "NODE-31 P0 keeps NODE-29 root-to-leaf delegation only"
            )

        effective_root_tools = _ordered_intersection(
            definition.allowed_tools,
            context.allowed_tools,
        )
        root_model = await self.base_factory.models.model_for_root(
            model_profile=definition.model_profile,
            context=context,
        )
        _assert_gateway_model(root_model, profile=definition.model_profile)
        root_tools = await self.base_factory.tools.tools_for_root(
            context=context,
            allowed_tools=effective_root_tools,
        )
        _assert_gateway_tools(root_tools, expected=effective_root_tools)
        backend = await self.base_factory.backends.backend_for_run(
            context=context,
            virtual_files_enabled=definition.virtual_files_enabled,
        )
        _assert_backend(backend)
        checkpointer = await self.base_factory.checkpointers.checkpointer_for_run(
            context=context
        )
        if checkpointer is None:
            raise DeepAgentFactoryError(
                "Skill-aware Deep Agent requires a NODE-28 checkpointer"
            )
        store = (
            await self.base_factory.stores.store_for_run(context=context)
            if self.base_factory.stores is not None
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
            )
            child_model = await self.base_factory.models.model_for_subagent(
                definition=child,
                context=child_context,
            )
            _assert_gateway_model(child_model, profile=child.model_profile)
            child_tools = await self.base_factory.tools.tools_for_subagent(
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
        parameters = inspect.signature(create_deep_agent).parameters
        if "skills" not in parameters:
            raise DeepAgentFactoryError(
                "installed Deep Agents does not support required skills parameter"
            )
        kwargs: dict[str, Any] = {
            "model": root_model,
            "tools": list(root_tools),
            "system_prompt": definition.system_prompt,
            "subagents": subagent_configs,
            "backend": backend,
            "checkpointer": checkpointer,
            "skills": list(bundle.sources),
        }
        if "name" in parameters:
            kwargs["name"] = definition.agent_key
        if store is not None:
            if "store" not in parameters:
                raise DeepAgentFactoryError(
                    "installed Deep Agents does not support required store parameter"
                )
            kwargs["store"] = store
        try:
            compiled = create_deep_agent(**kwargs)
        except Exception as exc:
            raise DeepAgentFactoryError(
                "Skill-aware Deep Agents compilation failed"
            ) from exc
        if getattr(compiled, "checkpointer", None) is None:
            raise DeepAgentFactoryError(
                "compiled Skill-aware Deep Agent lost durable checkpointer"
            )

        graph_metadata = {
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
            "delegation_max_total_calls": (
                definition.delegation.max_total_subagent_calls
            ),
            "skill_pack_freeze_hash": bundle.pack.freeze_hash,
            "resolved_skills": [
                {
                    "id": item.definition.skill_id,
                    "version": item.definition.version,
                    "hash": item.definition.content_hash,
                }
                for item in bundle.pack.skills
            ],
        }
        graph_definition = GraphDefinition(
            graph_key=definition.graph_key,
            graph_version=definition.graph_version,
            agent_config_version=definition.agent_config_version,
            description=f"Deep Agent runtime {definition.identity} with Skill pack",
            state_schema_version=1,
            interrupt_policy_version="deep-runtime-v1",
            metadata=graph_metadata,
        )
        limited = LimitedCompiledDeepAgent(
            compiled,
            recursion_limit=definition.max_steps,
            max_concurrency=definition.delegation.max_parallel_subagents,
        )
        return CompiledDeepAgent(
            definition=definition,
            graph_definition=graph_definition,
            compiled_graph=limited,
            effective_root_tools=effective_root_tools,
            subagent_tools=subagent_tools,
        )

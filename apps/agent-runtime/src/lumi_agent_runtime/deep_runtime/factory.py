from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from importlib import import_module
from typing import Any, AsyncIterator

from .contracts import (
    DeepAgentInvocationContext,
    DeepAgentProvenance,
    MaterializedSkill,
    PinnedContextBundle,
    ResolvedAgentConfig,
)
from .errors import (
    DeepAgentDelegationDeniedError,
    DeepAgentFactoryError,
    DeepAgentModelBoundaryError,
    DeepAgentPermissionError,
)
from .filesystem import ScopedWorkspacePolicy, assert_trusted_backend
from .ports import (
    DeepAgentBackendProvider,
    DeepAgentCheckpointerProvider,
    DeepAgentModelProvider,
    DeepAgentStoreProvider,
    DeepAgentToolProvider,
    RunBudgetMeter,
)
from .prompting import build_system_prompt
from .structured_result import AGENT_TASK_RESULT_SCHEMA
from .tooling import assert_gateway_tools


@dataclass(frozen=True, slots=True)
class CompiledDeepAgent:
    config: ResolvedAgentConfig
    compiled_graph: Any
    provenance: DeepAgentProvenance
    thread_id: str
    effective_tools: tuple[str, ...]

    async def ainvoke(self, value: Any) -> Any:
        return await self.compiled_graph.ainvoke(
            value,
            config=self._runtime_config(),
        )

    async def astream(self, value: Any) -> AsyncIterator[Any]:
        async for chunk in self.compiled_graph.astream(
            value,
            config=self._runtime_config(),
        ):
            yield chunk

    def _runtime_config(self) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": self.config.max_steps,
            "metadata": {
                "lumi_agent_id": self.config.agent_id,
                "lumi_agent_version": self.config.exact_version,
            },
        }


class LumiDeepAgentFactory:
    def __init__(
        self,
        *,
        models: DeepAgentModelProvider,
        tools: DeepAgentToolProvider,
        backends: DeepAgentBackendProvider,
        checkpointers: DeepAgentCheckpointerProvider,
        budget: RunBudgetMeter,
        stores: DeepAgentStoreProvider | None = None,
    ) -> None:
        self.models = models
        self.tools = tools
        self.backends = backends
        self.checkpointers = checkpointers
        self.budget = budget
        self.stores = stores

    async def compile(
        self,
        *,
        config: ResolvedAgentConfig,
        context: DeepAgentInvocationContext,
        bundle: PinnedContextBundle,
        skills: tuple[MaterializedSkill, ...],
    ) -> CompiledDeepAgent:
        _validate_permissions(config, context)
        effective_tools = tuple(
            item
            for item in config.allowed_tools
            if item in context.permissions.allowed_tools
        )
        _validate_skills(skills, effective_tools, context)
        warning = await self.budget.warning(context=context)

        root_model = await self.models.model_for_root(
            model_profile=config.model_profile,
            context=context,
        )
        _assert_model(root_model, config.model_profile)
        root_tools = await self.tools.tools_for_root(
            context=context,
            allowed_tools=effective_tools,
        )
        root_tool_versions = assert_gateway_tools(root_tools, effective_tools)

        backend = await self.backends.backend_for_run(
            context=context,
            skills=skills,
            bundle=bundle,
        )
        assert_trusted_backend(
            backend,
            ScopedWorkspacePolicy(context.permissions),
        )
        checkpointer = await self.checkpointers.checkpointer_for_run(
            context=context
        )
        if checkpointer is None:
            raise DeepAgentFactoryError("durable checkpointer is required")
        store = (
            await self.stores.store_for_run(context=context)
            if self.stores is not None
            else None
        )

        subagent_configs: list[dict[str, Any]] = []
        subagent_tool_versions: list[str] = []
        allowed_subagents = set(context.permissions.allowed_subagents)
        for child in config.subagents:
            if child.agent_id not in allowed_subagents:
                continue
            child_tools_scope = tuple(
                item for item in child.allowed_tools if item in effective_tools
            )
            child_model = await self.models.model_for_subagent(
                definition=child,
                context=context,
            )
            _assert_model(child_model, child.model_profile)
            child_tools = await self.tools.tools_for_subagent(
                context=context,
                definition=child,
                allowed_tools=child_tools_scope,
            )
            subagent_tool_versions.extend(
                assert_gateway_tools(child_tools, child_tools_scope)
            )
            subagent_configs.append(
                {
                    "name": child.agent_id,
                    "description": child.description,
                    "system_prompt": child.system_prompt,
                    "model": child_model,
                    "tools": list(child_tools),
                }
            )

        deep_factory = _load_create_deep_agent()
        parameters = _require_factory_contract(deep_factory)
        system_prompt = build_system_prompt(
            config=config,
            context=context,
            bundle=bundle,
            skills=skills,
            budget_warning=warning,
        )
        kwargs: dict[str, Any] = {
            "model": root_model,
            "tools": list(root_tools),
            "system_prompt": system_prompt,
            "subagents": subagent_configs,
            "backend": backend,
            "checkpointer": checkpointer,
        }
        if "name" in parameters:
            kwargs["name"] = config.agent_id
        if skills:
            if "skills" not in parameters:
                raise DeepAgentFactoryError(
                    "installed Deep Agents lacks native skills"
                )
            kwargs["skills"] = ["/skills/"]
        if "response_format" in parameters:
            kwargs["response_format"] = AGENT_TASK_RESULT_SCHEMA
        if store is not None:
            if "store" not in parameters:
                raise DeepAgentFactoryError(
                    "installed Deep Agents lacks store support"
                )
            kwargs["store"] = store
        try:
            compiled = deep_factory(**kwargs)
        except Exception as exc:
            raise DeepAgentFactoryError(
                "Deep Agents factory compilation failed"
            ) from exc
        if getattr(compiled, "checkpointer", None) is None:
            raise DeepAgentFactoryError(
                "compiled Deep Agent lost durable checkpointer"
            )

        skill_versions = tuple(
            f"{item.skill_id}@{item.exact_version}" for item in skills
        )
        all_tool_versions = root_tool_versions + tuple(
            subagent_tool_versions
        )
        tool_versions = tuple(dict.fromkeys(all_tool_versions))
        provenance = DeepAgentProvenance(
            agent_id=config.agent_id,
            agent_version=config.exact_version,
            agent_config_hash=config.content_hash,
            context_bundle_ref=bundle.context_bundle_ref,
            context_hash=bundle.content_hash,
            skill_versions=skill_versions,
            tool_versions=tool_versions,
            model_profile=config.model_profile,
            sandbox_execute=context.permissions.sandbox_execute,
        )
        thread_id = (
            f"deep:{context.agent_run_id}:{context.task_id or 'no-task'}:"
            f"{config.agent_id}:{config.exact_version}"
        )
        return CompiledDeepAgent(
            config=config,
            compiled_graph=compiled,
            provenance=provenance,
            thread_id=thread_id,
            effective_tools=effective_tools,
        )


def _validate_permissions(
    config: ResolvedAgentConfig,
    context: DeepAgentInvocationContext,
) -> None:
    scope = context.permissions
    if context.root_agent != config.agent_id:
        raise DeepAgentPermissionError(
            "runtime root agent differs from resolved config"
        )
    if not re.fullmatch(r"[0-9a-f]{64}", config.content_hash):
        raise DeepAgentPermissionError(
            "resolved agent config lacks immutable content hash"
        )
    if config.output_schema != "AgentTaskResult":
        raise DeepAgentPermissionError(
            "NODE-29 requires AgentTaskResult output schema"
        )
    if config.delegation.max_depth > 1:
        raise DeepAgentDelegationDeniedError(
            "NODE-29 P0 allows root-to-leaf delegation only"
        )
    if not set(scope.allowed_tools) <= set(config.allowed_tools):
        raise DeepAgentPermissionError(
            "runtime tool scope expands agent config"
        )
    if scope.sandbox_execute and not config.sandbox_execute:
        raise DeepAgentPermissionError(
            "runtime sandbox permission expands agent config"
        )
    if not set(scope.memory_read_scopes) <= set(config.memory_read_scopes):
        raise DeepAgentPermissionError(
            "runtime memory read scope expands agent config"
        )
    if not set(scope.memory_write_scopes) <= set(
        config.memory_write_scopes
    ):
        raise DeepAgentPermissionError(
            "runtime memory write scope expands agent config"
        )
    configured_children = {item.agent_id for item in config.subagents}
    if not set(scope.allowed_subagents) <= configured_children:
        raise DeepAgentDelegationDeniedError(
            "runtime subagent scope expands agent config"
        )
    if scope.allowed_subagents and config.delegation.max_depth < 1:
        raise DeepAgentDelegationDeniedError(
            "delegation disabled by agent config"
        )


def _validate_skills(
    skills: tuple[MaterializedSkill, ...],
    effective_tools: tuple[str, ...],
    context: DeepAgentInvocationContext,
) -> None:
    effective = set(effective_tools)
    for skill in skills:
        if not set(skill.required_tools) <= effective:
            raise DeepAgentPermissionError(
                "skill expands tool permission: "
                f"{skill.skill_id}@{skill.exact_version}"
            )
        for permission in skill.required_permissions:
            if (
                permission == "sandbox.execute"
                and not context.permissions.sandbox_execute
            ):
                raise DeepAgentPermissionError(
                    "skill requires ungranted sandbox permission: "
                    f"{skill.skill_id}"
                )
            if permission.startswith("memory.write:"):
                scope = permission.removeprefix("memory.write:")
                if scope not in context.permissions.memory_write_scopes:
                    raise DeepAgentPermissionError(
                        "skill requires ungranted memory scope: "
                        f"{skill.skill_id}"
                    )


def _assert_model(model: Any, profile: str) -> None:
    if not bool(getattr(model, "_lumi_model_gateway_bound", False)):
        raise DeepAgentModelBoundaryError(
            f"model profile {profile} bypasses NODE-22 Model Gateway"
        )
    if not bool(getattr(model, "_lumi_budget_meter_bound", False)):
        raise DeepAgentModelBoundaryError(
            f"model profile {profile} lacks server-side run budget metering"
        )


def _load_create_deep_agent() -> Any:
    try:
        module = import_module("deepagents")
        return module.create_deep_agent  # type: ignore[attr-defined]
    except (ImportError, AttributeError) as exc:
        raise DeepAgentFactoryError(
            "deepagents.create_deep_agent is required"
        ) from exc


def _require_factory_contract(factory: Any) -> dict[str, inspect.Parameter]:
    try:
        parameters = dict(inspect.signature(factory).parameters)
    except (TypeError, ValueError) as exc:
        raise DeepAgentFactoryError(
            "cannot inspect create_deep_agent signature"
        ) from exc
    required = {
        "model",
        "tools",
        "system_prompt",
        "subagents",
        "backend",
        "checkpointer",
    }
    missing = required - set(parameters)
    if missing:
        raise DeepAgentFactoryError(
            "installed Deep Agents factory missing: "
            + ",".join(sorted(missing))
        )
    return parameters

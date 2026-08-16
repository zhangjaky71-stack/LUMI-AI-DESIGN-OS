from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from importlib import import_module
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from .contracts import (
    DeepAgentInvocationContext,
    DeepAgentProvenance,
    MaterializedSkill,
    PinnedContextBundle,
    ResolvedAgentConfig,
    ResolvedSubagent,
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
from .prompting import build_subagent_system_prompt, build_system_prompt
from .structured_result import AGENT_TASK_RESULT_SCHEMA
from .tooling import assert_gateway_tools

_GENERAL_PURPOSE = "general-purpose"


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
        skill_lookup = _skill_lookup(skills)
        root_skills = _skills_for_refs(config.skill_refs, skill_lookup)
        _validate_skill_permissions(
            root_skills,
            allowed_tools=effective_tools,
            context=context,
            leaf=False,
        )
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

        permission_type = _load_filesystem_permission_type()
        root_skill_sources = _skill_sources(root_skills)
        root_permissions = _filesystem_permissions(
            permission_type,
            skill_sources=root_skill_sources,
            allow_memory_read=bool(context.permissions.memory_read_scopes),
            allow_memory_write=bool(context.permissions.memory_write_scopes),
        )

        subagent_configs: list[dict[str, Any]] = [
            _disabled_general_purpose_subagent()
        ]
        subagent_tool_versions: list[str] = []
        allowed_subagents = set(context.permissions.allowed_subagents)
        consumed_skill_refs = set(config.skill_refs)
        for child in config.subagents:
            if child.agent_id not in allowed_subagents:
                continue
            child_tools_scope = tuple(
                item for item in child.allowed_tools if item in effective_tools
            )
            child_skills = _skills_for_refs(child.skill_refs, skill_lookup)
            consumed_skill_refs.update(child.skill_refs)
            _validate_skill_permissions(
                child_skills,
                allowed_tools=child_tools_scope,
                context=context,
                leaf=True,
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
            child_sources = _skill_sources(child_skills)
            subagent_configs.append(
                {
                    "name": child.agent_id,
                    "description": child.description,
                    "system_prompt": build_subagent_system_prompt(
                        definition=child,
                        bundle=bundle,
                        allowed_tools=child_tools_scope,
                        skills=child_skills,
                    ),
                    "model": child_model,
                    "tools": list(child_tools),
                    "skills": list(child_sources),
                    "permissions": _filesystem_permissions(
                        permission_type,
                        skill_sources=child_sources,
                        allow_memory_read=False,
                        allow_memory_write=False,
                    ),
                    "response_format": AGENT_TASK_RESULT_SCHEMA,
                }
            )

        _assert_no_extra_materialized_skills(
            skills,
            consumed_skill_refs,
        )

        deep_factory = _load_create_deep_agent()
        parameters = _require_factory_contract(deep_factory)
        system_prompt = build_system_prompt(
            config=config,
            context=context,
            bundle=bundle,
            skills=root_skills,
            budget_warning=warning,
        )
        kwargs: dict[str, Any] = {
            "model": root_model,
            "tools": list(root_tools),
            "system_prompt": system_prompt,
            "subagents": subagent_configs,
            "backend": backend,
            "permissions": root_permissions,
            "checkpointer": checkpointer,
        }
        if "name" in parameters:
            kwargs["name"] = config.agent_id
        if root_skill_sources:
            if "skills" not in parameters:
                raise DeepAgentFactoryError(
                    "installed Deep Agents lacks native skills"
                )
            kwargs["skills"] = list(root_skill_sources)
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
    configured_children = {item.agent_id for item in config.subagents}
    if _GENERAL_PURPOSE in configured_children:
        raise DeepAgentDelegationDeniedError(
            "general-purpose is reserved for the LUMI disabled safety shim"
        )
    if not set(scope.allowed_tools) <= set(config.allowed_tools):
        raise DeepAgentPermissionError(
            "runtime tool scope expands agent config"
        )
    if scope.sandbox_execute and not config.sandbox_execute:
        raise DeepAgentPermissionError(
            "runtime sandbox permission expands agent config"
        )
    if scope.sandbox_execute and scope.allowed_subagents:
        raise DeepAgentDelegationDeniedError(
            "P0 sandbox execute cannot be combined with synchronous subagents"
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
    if not set(scope.allowed_subagents) <= configured_children:
        raise DeepAgentDelegationDeniedError(
            "runtime subagent scope expands agent config"
        )
    if scope.allowed_subagents and config.delegation.max_depth < 1:
        raise DeepAgentDelegationDeniedError(
            "delegation disabled by agent config"
        )


def _skill_lookup(
    skills: tuple[MaterializedSkill, ...],
) -> dict[str, MaterializedSkill]:
    lookup: dict[str, MaterializedSkill] = {}
    for skill in skills:
        ref = f"{skill.skill_id}@{skill.exact_version}"
        if ref in lookup:
            raise DeepAgentPermissionError(
                f"duplicate materialized skill: {ref}"
            )
        lookup[ref] = skill
    return lookup


def _skills_for_refs(
    refs: tuple[str, ...],
    lookup: dict[str, MaterializedSkill],
) -> tuple[MaterializedSkill, ...]:
    resolved: list[MaterializedSkill] = []
    for ref in refs:
        try:
            resolved.append(lookup[ref])
        except KeyError as exc:
            raise DeepAgentPermissionError(
                f"exact materialized skill missing: {ref}"
            ) from exc
    return tuple(resolved)


def _skill_sources(
    skills: tuple[MaterializedSkill, ...],
) -> tuple[str, ...]:
    sources: list[str] = []
    for skill in skills:
        if not skill.path.endswith("/SKILL.md"):
            raise DeepAgentPermissionError(
                f"skill path must end with SKILL.md: {skill.path}"
            )
        source = skill.path.rsplit("/", 1)[0] + "/"
        sources.append(source)
    return tuple(dict.fromkeys(sources))


def _validate_skill_permissions(
    skills: tuple[MaterializedSkill, ...],
    *,
    allowed_tools: tuple[str, ...],
    context: DeepAgentInvocationContext,
    leaf: bool,
) -> None:
    effective = set(allowed_tools)
    for skill in skills:
        if not set(skill.required_tools) <= effective:
            raise DeepAgentPermissionError(
                "skill expands tool permission: "
                f"{skill.skill_id}@{skill.exact_version}"
            )
        for permission in skill.required_permissions:
            if permission == "sandbox.execute":
                if leaf or not context.permissions.sandbox_execute:
                    raise DeepAgentPermissionError(
                        "skill requires ungranted sandbox permission: "
                        f"{skill.skill_id}"
                    )
            if permission.startswith("memory.write:"):
                if leaf:
                    raise DeepAgentPermissionError(
                        "leaf subagent skills cannot write memory in P0"
                    )
                scope = permission.removeprefix("memory.write:")
                if scope not in context.permissions.memory_write_scopes:
                    raise DeepAgentPermissionError(
                        "skill requires ungranted memory scope: "
                        f"{skill.skill_id}"
                    )


def _assert_no_extra_materialized_skills(
    skills: tuple[MaterializedSkill, ...],
    consumed_refs: set[str],
) -> None:
    actual = {
        f"{skill.skill_id}@{skill.exact_version}" for skill in skills
    }
    if actual != consumed_refs:
        raise DeepAgentPermissionError(
            "materialized skills differ from exact allowed set: "
            f"{sorted(actual)} != {sorted(consumed_refs)}"
        )


def _filesystem_permissions(
    permission_type: Any,
    *,
    skill_sources: tuple[str, ...],
    allow_memory_read: bool,
    allow_memory_write: bool,
) -> list[Any]:
    read_roots = [
        "/workspace/input",
        "/workspace/work",
        "/workspace/output",
        *[source.rstrip("/") for source in skill_sources],
    ]
    write_roots = ["/workspace/work", "/workspace/output"]
    if allow_memory_read:
        read_roots.append("/memory")
    if allow_memory_write:
        write_roots.append("/memory")
    rules: list[Any] = []
    if read_roots:
        rules.append(
            permission_type(
                operations=["read"],
                paths=_permission_paths(read_roots),
                mode="allow",
            )
        )
    if write_roots:
        rules.append(
            permission_type(
                operations=["write"],
                paths=_permission_paths(write_roots),
                mode="allow",
            )
        )
    rules.append(
        permission_type(
            operations=["read", "write"],
            paths=["/**"],
            mode="deny",
        )
    )
    return rules


def _permission_paths(roots: list[str]) -> list[str]:
    paths: list[str] = []
    for root in roots:
        normalized = root.rstrip("/")
        paths.extend((normalized, normalized + "/**"))
    return list(dict.fromkeys(paths))


def _disabled_general_purpose_subagent() -> dict[str, Any]:
    def deny(_state: Any) -> dict[str, Any]:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "General-purpose delegation is disabled by LUMI policy. "
                        "Use one of the exact registered specialist subagents."
                    )
                )
            ]
        }

    return {
        "name": _GENERAL_PURPOSE,
        "description": (
            "Disabled safety target. Do not delegate work here; choose an exact "
            "registered specialist subagent instead."
        ),
        "runnable": RunnableLambda(deny),
    }


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


def _load_filesystem_permission_type() -> Any:
    try:
        module = import_module("deepagents")
        return module.FilesystemPermission  # type: ignore[attr-defined]
    except (ImportError, AttributeError) as exc:
        raise DeepAgentFactoryError(
            "deepagents.FilesystemPermission is required"
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
        "skills",
        "permissions",
        "backend",
        "response_format",
        "checkpointer",
        "store",
    }
    missing = required - set(parameters)
    if missing:
        raise DeepAgentFactoryError(
            "installed Deep Agents factory missing: "
            + ",".join(sorted(missing))
        )
    return parameters

from __future__ import annotations

from typing import Any, Protocol

from .contracts import (
    AgentTaskResult,
    DeepAgentInvocationContext,
    DeepAgentTaskRequest,
    MaterializedSkill,
    PinnedContextBundle,
    ResolvedAgentConfig,
    ResolvedSubagent,
    StoredAgentResult,
)


class AgentConfigResolver(Protocol):
    async def resolve(
        self,
        *,
        agent_ref: str,
        context: DeepAgentInvocationContext,
    ) -> ResolvedAgentConfig: ...


class SkillMaterializer(Protocol):
    async def materialize(
        self,
        *,
        skill_refs: tuple[str, ...],
        agent: ResolvedAgentConfig,
        context: DeepAgentInvocationContext,
    ) -> tuple[MaterializedSkill, ...]: ...


class ContextBundleProvider(Protocol):
    async def load(
        self,
        *,
        context_bundle_ref: str,
        context: DeepAgentInvocationContext,
    ) -> PinnedContextBundle: ...


class DeepAgentModelProvider(Protocol):
    async def model_for_root(
        self,
        *,
        model_profile: str,
        context: DeepAgentInvocationContext,
    ) -> Any: ...

    async def model_for_subagent(
        self,
        *,
        definition: ResolvedSubagent,
        context: DeepAgentInvocationContext,
    ) -> Any: ...


class DeepAgentToolProvider(Protocol):
    async def tools_for_root(
        self,
        *,
        context: DeepAgentInvocationContext,
        allowed_tools: tuple[str, ...],
    ) -> tuple[Any, ...]: ...

    async def tools_for_subagent(
        self,
        *,
        context: DeepAgentInvocationContext,
        definition: ResolvedSubagent,
        allowed_tools: tuple[str, ...],
    ) -> tuple[Any, ...]: ...


class DeepAgentBackendProvider(Protocol):
    async def backend_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
        skills: tuple[MaterializedSkill, ...],
        bundle: PinnedContextBundle,
    ) -> Any: ...


class DeepAgentCheckpointerProvider(Protocol):
    async def checkpointer_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
    ) -> Any: ...


class DeepAgentStoreProvider(Protocol):
    async def store_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
    ) -> Any: ...


class RunBudgetMeter(Protocol):
    async def before_model_call(
        self,
        *,
        context: DeepAgentInvocationContext,
        actor_agent: str,
        model_profile: str,
    ) -> None: ...

    async def before_tool_call(
        self,
        *,
        context: DeepAgentInvocationContext,
        actor_agent: str,
        tool_name: str,
    ) -> None: ...

    async def after_tool_call(
        self,
        *,
        context: DeepAgentInvocationContext,
        actor_agent: str,
        tool_name: str,
        succeeded: bool,
    ) -> None: ...

    async def warning(
        self,
        *,
        context: DeepAgentInvocationContext,
    ) -> str | None: ...


class LargeResultOffloader(Protocol):
    async def normalize(
        self,
        *,
        context: DeepAgentInvocationContext,
        actor_agent: str,
        tool_name: str,
        result: Any,
    ) -> Any: ...


class StructuredOutputRepairer(Protocol):
    async def repair(
        self,
        *,
        context: DeepAgentInvocationContext,
        invalid_value: Any,
        error_code: str,
    ) -> Any: ...


class AgentResultStore(Protocol):
    async def store(
        self,
        *,
        request: DeepAgentTaskRequest,
        result: AgentTaskResult,
        provenance: Any,
    ) -> StoredAgentResult: ...


class AgentTaskRequestResolver(Protocol):
    async def resolve(self, state: dict[str, Any]) -> DeepAgentTaskRequest: ...

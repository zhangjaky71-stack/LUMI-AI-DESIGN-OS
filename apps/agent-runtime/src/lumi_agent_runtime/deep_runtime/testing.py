from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from .contracts import (
    AgentTaskResult,
    DeepAgentInvocationContext,
    DeepAgentProvenance,
    DeepAgentTaskRequest,
    MaterializedSkill,
    PinnedContextBundle,
    ResolvedAgentConfig,
    StoredAgentResult,
)
from .errors import DeepAgentBudgetExceeded
from .filesystem import mark_trusted_backend


class FakeModel:
    def __init__(self) -> None:
        self._lumi_model_gateway_bound = True
        self._lumi_budget_meter_bound = True


class FakeTool:
    def __init__(self, name: str, version: str = "1.0.0") -> None:
        self._lumi_tool_gateway_bound = True
        self._lumi_tool_name = name
        self._lumi_tool_version = version


class FakeModelProvider:
    async def model_for_root(
        self,
        *,
        model_profile: str,
        context: Any,
    ) -> Any:
        del model_profile, context
        return FakeModel()

    async def model_for_subagent(
        self,
        *,
        definition: Any,
        context: Any,
    ) -> Any:
        del definition, context
        return FakeModel()


class FakeToolProvider:
    async def tools_for_root(
        self,
        *,
        context: Any,
        allowed_tools: tuple[str, ...],
    ) -> tuple[Any, ...]:
        del context
        return tuple(FakeTool(item) for item in allowed_tools)

    async def tools_for_subagent(
        self,
        *,
        context: Any,
        definition: Any,
        allowed_tools: tuple[str, ...],
    ) -> tuple[Any, ...]:
        del context, definition
        return tuple(FakeTool(item) for item in allowed_tools)


class FakeBackendProvider:
    async def backend_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
        skills: tuple[MaterializedSkill, ...],
        bundle: PinnedContextBundle,
    ) -> Any:
        del skills, bundle
        backend = SimpleNamespace()
        return mark_trusted_backend(
            backend,
            permissions=context.permissions,
            sandbox_execute_bound=context.permissions.sandbox_execute,
        )


@dataclass(slots=True)
class FakeCheckpointerProvider:
    checkpointer: Any = object()

    async def checkpointer_for_run(self, *, context: Any) -> Any:
        del context
        return self.checkpointer


class MemoryBudgetMeter:
    def __init__(
        self,
        *,
        tool_calls_left: int = 100,
        warning: str | None = None,
    ) -> None:
        self.tool_calls_left = tool_calls_left
        self.warning_text = warning
        self.calls: list[tuple[str, str]] = []

    async def before_model_call(
        self,
        *,
        context: Any,
        actor_agent: str,
        model_profile: str,
    ) -> None:
        del context
        self.calls.append((actor_agent, f"model:{model_profile}"))

    async def before_tool_call(
        self,
        *,
        context: Any,
        actor_agent: str,
        tool_name: str,
    ) -> None:
        del context
        if self.tool_calls_left <= 0:
            raise DeepAgentBudgetExceeded(
                "run budget exhausted before tool call"
            )
        self.tool_calls_left -= 1
        self.calls.append((actor_agent, f"tool:{tool_name}"))

    async def after_tool_call(
        self,
        *,
        context: Any,
        actor_agent: str,
        tool_name: str,
        succeeded: bool,
    ) -> None:
        del context, succeeded
        self.calls.append((actor_agent, f"settle:{tool_name}"))

    async def warning(self, *, context: Any) -> str | None:
        del context
        return self.warning_text


class MemoryOffloader:
    def __init__(self, threshold: int = 256) -> None:
        self.threshold = threshold
        self.offloaded = 0

    async def normalize(
        self,
        *,
        context: DeepAgentInvocationContext,
        actor_agent: str,
        tool_name: str,
        result: Any,
    ) -> Any:
        del actor_agent
        encoded = json.dumps(result, default=str, ensure_ascii=False)
        if len(encoded.encode()) <= self.threshold:
            return result
        self.offloaded += 1
        return {
            "summary": f"Large {tool_name} result offloaded",
            "ref": (
                f"tool-result://{context.agent_run_id}/{self.offloaded}"
            ),
        }


@dataclass(slots=True)
class StaticAgentResolver:
    config: ResolvedAgentConfig

    async def resolve(
        self,
        *,
        agent_ref: str,
        context: Any,
    ) -> ResolvedAgentConfig:
        del context
        if agent_ref != self.config.identity:
            raise KeyError(agent_ref)
        return self.config


@dataclass(slots=True)
class StaticSkillMaterializer:
    skills: tuple[MaterializedSkill, ...]

    async def materialize(self, **_: Any) -> tuple[MaterializedSkill, ...]:
        return self.skills


@dataclass(slots=True)
class StaticContextProvider:
    bundle: PinnedContextBundle

    async def load(self, **_: Any) -> PinnedContextBundle:
        return self.bundle


@dataclass(slots=True)
class StaticRequestResolver:
    request: DeepAgentTaskRequest

    async def resolve(self, state: dict[str, Any]) -> DeepAgentTaskRequest:
        del state
        return self.request


class MemoryResultStore:
    def __init__(self) -> None:
        self.items: list[StoredAgentResult] = []

    async def store(
        self,
        *,
        request: DeepAgentTaskRequest,
        result: AgentTaskResult,
        provenance: DeepAgentProvenance,
    ) -> StoredAgentResult:
        result_ref = (
            f"agent-result://{request.invocation.agent_run_id}/"
            f"{len(self.items) + 1}"
        )
        item = StoredAgentResult(
            result_ref=result_ref,
            result=result,
            provenance=provenance,
        )
        self.items.append(item)
        return item


@dataclass(slots=True)
class OneShotRepairer:
    repaired: Any
    calls: int = 0

    async def repair(self, **_: Any) -> Any:
        self.calls += 1
        return self.repaired


class FakeCompiledGraph:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.invocations: list[tuple[Any, Any]] = []
        self.checkpointer = object()

    async def ainvoke(self, value: Any, config: Any = None) -> Any:
        self.invocations.append((value, config))
        return self.result

    async def astream(self, value: Any, config: Any = None):
        self.invocations.append((value, config))
        yield self.result


@dataclass(slots=True)
class StaticCompiledFactory:
    compiled: Any

    async def compile(self, **_: Any) -> Any:
        return self.compiled


def money(value: str) -> Decimal:
    return Decimal(value)

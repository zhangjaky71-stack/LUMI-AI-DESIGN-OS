from __future__ import annotations

from typing import Any

from .contracts import AgentTaskStatus, DeepAgentTaskRequest, MaterializedSkill
from .errors import DeepAgentConfigurationError, DeepAgentExecutionError
from .factory import LumiDeepAgentFactory
from .ports import (
    AgentConfigResolver,
    AgentResultStore,
    AgentTaskRequestResolver,
    ContextBundleProvider,
    SkillMaterializer,
)
from .prompting import build_user_task
from .structured_result import StructuredResultParser


class DeepAgentTaskExecutor:
    """NODE-28 TaskPort adapter for one bounded Deep Agent task."""

    def __init__(
        self,
        *,
        requests: AgentTaskRequestResolver,
        agents: AgentConfigResolver,
        skills: SkillMaterializer,
        contexts: ContextBundleProvider,
        factory: LumiDeepAgentFactory,
        parser: StructuredResultParser,
        results: AgentResultStore,
    ) -> None:
        self.requests = requests
        self.agents = agents
        self.skills = skills
        self.contexts = contexts
        self.factory = factory
        self.parser = parser
        self.results = results

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        request = await self.requests.resolve(state)
        _assert_state_identity(state, request)
        config = await self.agents.resolve(
            agent_ref=request.agent_ref,
            context=request.invocation,
        )
        if request.agent_ref != config.identity:
            raise DeepAgentConfigurationError("agent resolver must freeze an exact version")
        skill_refs = _selected_skill_refs(config, request)
        materialized = await self.skills.materialize(
            skill_refs=skill_refs,
            agent=config,
            context=request.invocation,
        )
        _assert_exact_skills(skill_refs, materialized)
        bundle = await self.contexts.load(
            context_bundle_ref=request.context_bundle_ref,
            context=request.invocation,
        )
        if bundle.context_bundle_ref != request.context_bundle_ref:
            raise DeepAgentConfigurationError("Context Compiler returned a different bundle")
        compiled = await self.factory.compile(
            config=config,
            context=request.invocation,
            bundle=bundle,
            skills=materialized,
        )
        task_message = build_user_task(objective=request.objective, bundle=bundle)
        invoke_input = {"messages": [{"role": "user", "content": task_message}]}
        invoke_config = {
            "configurable": {"thread_id": compiled.thread_id},
            "recursion_limit": config.max_steps,
            "metadata": {
                "lumi_agent_run_id": str(request.invocation.agent_run_id),
                "lumi_task_id": str(request.invocation.task_id or ""),
                "lumi_agent_id": config.agent_id,
                "lumi_agent_version": config.exact_version,
            },
        }
        try:
            raw = await compiled.compiled_graph.ainvoke(invoke_input, config=invoke_config)
        except Exception as exc:
            raise DeepAgentExecutionError("Deep Agent task invocation failed") from exc
        result = await self.parser.parse(raw_result=raw, context=request.invocation)
        stored = await self.results.store(
            request=request,
            result=result,
            provenance=compiled.provenance,
        )
        return _safe_control_delta(state, stored.result_ref, result)


def _assert_state_identity(state: dict[str, Any], request: DeepAgentTaskRequest) -> None:
    expected = {
        "run_id": str(request.invocation.agent_run_id),
        "organization_id": str(request.invocation.organization_id),
        "project_id": str(request.invocation.project_id),
    }
    for key, value in expected.items():
        if str(state.get(key)) != value:
            raise DeepAgentConfigurationError(f"NODE-28 state mismatch: {key}")
    task_id = state.get("task_id")
    expected_task = str(request.invocation.task_id) if request.invocation.task_id else None
    if task_id != expected_task:
        raise DeepAgentConfigurationError("NODE-28 state mismatch: task_id")


def _selected_skill_refs(config: Any, request: DeepAgentTaskRequest) -> tuple[str, ...]:
    allowed_subagents = set(request.invocation.permissions.allowed_subagents)
    values = list(config.skill_refs)
    for child in config.subagents:
        if child.agent_id in allowed_subagents:
            values.extend(child.skill_refs)
    return tuple(dict.fromkeys(values))


def _assert_exact_skills(
    requested: tuple[str, ...],
    materialized: tuple[MaterializedSkill, ...],
) -> None:
    expected = set(requested)
    actual = {f"{item.skill_id}@{item.exact_version}" for item in materialized}
    if expected != actual:
        raise DeepAgentConfigurationError(
            f"Skill Registry exact resolution mismatch: {sorted(expected)} != {sorted(actual)}"
        )


def _safe_control_delta(
    state: dict[str, Any],
    result_ref: str,
    result: Any,
) -> dict[str, Any]:
    artifacts = list(state.get("artifact_refs", []))
    artifacts.extend(result.artifact_refs)
    contexts = list(state.get("context_refs", []))
    contexts.extend(result.knowledge_refs)
    contexts.append(result_ref)
    delta: dict[str, Any] = {
        "artifact_refs": list(dict.fromkeys(artifacts)),
        "context_refs": list(dict.fromkeys(contexts)),
    }
    if result.status is AgentTaskStatus.FAILED:
        errors = list(state.get("errors", []))
        errors.append({"code": "DEEP_AGENT_TASK_FAILED", "result_ref": result_ref})
        delta["errors"] = errors
    return delta

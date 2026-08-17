from __future__ import annotations

from typing import Any, Protocol

from lumi_agent_runtime.deep_runtime.contracts import (
    AgentTaskStatus,
    DeepAgentTaskRequest,
    MaterializedSkill,
    PinnedContextBundle,
    ResolvedAgentConfig,
)
from lumi_agent_runtime.deep_runtime.errors import (
    DeepAgentConfigurationError,
    DeepAgentExecutionError,
)
from lumi_agent_runtime.deep_runtime.ports import (
    AgentConfigResolver,
    AgentResultStore,
    AgentTaskRequestResolver,
    ContextBundleProvider,
    SkillMaterializer,
)
from lumi_agent_runtime.deep_runtime.prompting import build_system_prompt

from .budget import TokenCounter, conservative_token_estimate
from .builder import ContextEngine
from .contracts import ContextManifest, ContextRequest
from .errors import ContextIntegrityError
from .profiles import BALANCED_CONTEXT_PROFILE, ContextProfile
from .store import RuntimeContextManifestStore


class DeepAgentContextRequestFactory(Protocol):
    async def create(
        self,
        *,
        request: DeepAgentTaskRequest,
        bundle: PinnedContextBundle,
        agent: ResolvedAgentConfig,
        skills: tuple[MaterializedSkill, ...],
    ) -> ContextRequest: ...


class DefaultDeepAgentContextRequestFactory:
    def __init__(
        self,
        *,
        max_input_tokens: int,
        profile: ContextProfile = BALANCED_CONTEXT_PROFILE,
        token_counter: TokenCounter = conservative_token_estimate,
        static_safety_margin_tokens: int = 128,
    ) -> None:
        if max_input_tokens < 1024:
            raise ValueError("CONTEXT_MODEL_INPUT_LIMIT_INVALID")
        if static_safety_margin_tokens < 0:
            raise ValueError("CONTEXT_STATIC_MARGIN_INVALID")
        self.max_input_tokens = max_input_tokens
        self.profile = profile
        self.token_counter = token_counter
        self.static_safety_margin_tokens = static_safety_margin_tokens

    async def create(
        self,
        *,
        request: DeepAgentTaskRequest,
        bundle: PinnedContextBundle,
        agent: ResolvedAgentConfig,
        skills: tuple[MaterializedSkill, ...],
    ) -> ContextRequest:
        static_prompt = build_system_prompt(
            config=agent,
            context=request.invocation,
            bundle=bundle,
            skills=skills,
            budget_warning=None,
        )
        static_tokens = (
            self.token_counter(static_prompt)
            + self.static_safety_margin_tokens
        )
        dynamic = (
            self.max_input_tokens
            - self.profile.response_reserve_tokens
            - static_tokens
        )
        budgets = self.profile.layer_budgets(dynamic)
        return ContextRequest(
            organization_id=request.invocation.organization_id,
            project_id=request.invocation.project_id,
            agent_run_id=request.invocation.agent_run_id,
            task_id=request.invocation.task_id,
            agent_ref=request.agent_ref,
            context_bundle_ref=request.context_bundle_ref,
            objective=request.objective,
            purpose="deep-agent-task",
            query=request.objective,
            max_input_tokens=self.max_input_tokens,
            response_reserve_tokens=self.profile.response_reserve_tokens,
            static_prompt_tokens=static_tokens,
            layer_budgets=budgets,
            memory_read_scopes=request.invocation.permissions.memory_read_scopes,
            retrieval_limit=self.profile.retrieval_limit,
            metadata={
                "context_profile": self.profile.name,
                "static_safety_margin_tokens": self.static_safety_margin_tokens,
            },
        )


class ContextAwareDeepAgentTaskExecutor:
    """NODE-34 composition adapter for NODE-29 + NODE-32 + NODE-33."""

    def __init__(
        self,
        *,
        requests: AgentTaskRequestResolver,
        agents: AgentConfigResolver,
        skills: SkillMaterializer,
        contexts: ContextBundleProvider,
        factory: Any,
        parser: Any,
        results: AgentResultStore,
        context_engine: ContextEngine,
        context_requests: DeepAgentContextRequestFactory,
        manifests: RuntimeContextManifestStore,
    ) -> None:
        self.requests = requests
        self.agents = agents
        self.skills = skills
        self.contexts = contexts
        self.factory = factory
        self.parser = parser
        self.results = results
        self.context_engine = context_engine
        self.context_requests = context_requests
        self.manifests = manifests

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        request = await self.requests.resolve(state)
        _assert_state_identity(state, request)
        config = await self.agents.resolve(
            agent_ref=request.agent_ref,
            context=request.invocation,
        )
        if request.agent_ref != config.identity:
            raise DeepAgentConfigurationError(
                "agent resolver must freeze an exact version"
            )

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
            raise DeepAgentConfigurationError(
                "Context Compiler returned a different bundle"
            )

        context_request = await self.context_requests.create(
            request=request,
            bundle=bundle,
            agent=config,
            skills=materialized,
        )
        manifest = await self.context_engine.build(
            request=context_request,
            bundle=bundle,
            agent=config,
            skills=materialized,
        )
        runtime_ref = await self.manifests.store(manifest)
        if runtime_ref != manifest.runtime_context_ref:
            raise ContextIntegrityError("CONTEXT_MANIFEST_STORE_REF_MISMATCH")

        compiled = await self.factory.compile(
            config=config,
            context=request.invocation,
            bundle=bundle,
            skills=materialized,
        )
        task_message = build_context_aware_user_task(
            objective=request.objective,
            manifest=manifest,
        )
        invoke_input = {
            "messages": [{"role": "user", "content": task_message}]
        }
        try:
            raw = await compiled.ainvoke(invoke_input)
        except Exception as exc:
            raise DeepAgentExecutionError(
                "Deep Agent task invocation failed"
            ) from exc

        result = await self.parser.parse(
            raw_result=raw,
            context=request.invocation,
        )
        stored = await self.results.store(
            request=request,
            result=result,
            provenance=compiled.provenance,
        )
        return _safe_control_delta(
            state=state,
            result_ref=stored.result_ref,
            runtime_context_ref=runtime_ref,
            result=result,
        )


def build_context_aware_user_task(
    *,
    objective: str,
    manifest: ContextManifest,
) -> str:
    return (
        "<task_request source=\"user-or-workflow\" "
        "instruction_priority=\"user\">\n"
        f"{objective}\n"
        "</task_request>\n\n"
        "<runtime_context source=\"context-engine\" "
        f"ref=\"{manifest.runtime_context_ref}\" "
        f"freeze_hash=\"{manifest.freeze_hash}\">\n"
        f"{manifest.rendered_context}\n"
        "</runtime_context>"
    )


def _assert_state_identity(
    state: dict[str, Any],
    request: DeepAgentTaskRequest,
) -> None:
    expected = {
        "run_id": str(request.invocation.agent_run_id),
        "organization_id": str(request.invocation.organization_id),
        "project_id": str(request.invocation.project_id),
    }
    for key, value in expected.items():
        if str(state.get(key)) != value:
            raise DeepAgentConfigurationError(
                f"NODE-28 state mismatch: {key}"
            )
    task_id = state.get("task_id")
    expected_task = (
        str(request.invocation.task_id)
        if request.invocation.task_id
        else None
    )
    if task_id != expected_task:
        raise DeepAgentConfigurationError(
            "NODE-28 state mismatch: task_id"
        )


def _selected_skill_refs(
    config: ResolvedAgentConfig,
    request: DeepAgentTaskRequest,
) -> tuple[str, ...]:
    allowed_subagents = set(
        request.invocation.permissions.allowed_subagents
    )
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
    actual = {
        f"{item.skill_id}@{item.exact_version}"
        for item in materialized
    }
    if expected != actual:
        raise DeepAgentConfigurationError(
            "Skill Registry exact resolution mismatch: "
            f"{sorted(expected)} != {sorted(actual)}"
        )


def _safe_control_delta(
    *,
    state: dict[str, Any],
    result_ref: str,
    runtime_context_ref: str,
    result: Any,
) -> dict[str, Any]:
    artifacts = list(state.get("artifact_refs", []))
    artifacts.extend(result.artifact_refs)
    contexts = list(state.get("context_refs", []))
    contexts.extend(result.knowledge_refs)
    contexts.extend((runtime_context_ref, result_ref))
    delta: dict[str, Any] = {
        "artifact_refs": list(dict.fromkeys(artifacts)),
        "context_refs": list(dict.fromkeys(contexts)),
    }
    if result.status is AgentTaskStatus.FAILED:
        errors = list(state.get("errors", []))
        errors.append(
            {
                "code": "DEEP_AGENT_TASK_FAILED",
                "result_ref": result_ref,
                "runtime_context_ref": runtime_context_ref,
            }
        )
        delta["errors"] = errors
    return delta

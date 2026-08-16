from __future__ import annotations

import asyncio
from uuid import uuid4

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentInvocationContext,
    DeepAgentProvenance,
    DeepAgentTaskRequest,
    MaterializedSkill,
    PermissionScope,
    PinnedContextBundle,
    ResolvedAgentConfig,
)
from lumi_agent_runtime.deep_runtime.executor import DeepAgentTaskExecutor
from lumi_agent_runtime.deep_runtime.factory import CompiledDeepAgent
from lumi_agent_runtime.deep_runtime.structured_result import (
    StructuredResultParser,
)
from lumi_agent_runtime.deep_runtime.testing import (
    FakeCompiledGraph,
    MemoryResultStore,
    StaticAgentResolver,
    StaticCompiledFactory,
    StaticContextProvider,
    StaticRequestResolver,
    StaticSkillMaterializer,
)


def test_autonomous_agentic_task_returns_only_safe_node28_delta() -> None:
    organization_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    task_id = uuid4()
    invocation = DeepAgentInvocationContext(
        organization_id=organization_id,
        project_id=project_id,
        agent_run_id=run_id,
        task_id=task_id,
        operation_id=uuid4(),
        actor_id="user:eval",
        root_agent="critic",
        permissions=PermissionScope(allowed_tools=("asset.read",)),
        budget_limit_usd="2.00",
    )
    request = DeepAgentTaskRequest(
        agent_ref="critic@1.0.0",
        objective=(
            "Critique the current poster and propose the most important "
            "correction."
        ),
        context_bundle_ref="context://eval/poster-1",
        invocation=invocation,
    )
    config = ResolvedAgentConfig(
        agent_id="critic",
        exact_version="1.0.0",
        role="Visual Critic",
        system_prompt=(
            "Evaluate hierarchy, readability, brand fit, and production risk."
        ),
        model_profile="balanced",
        allowed_tools=("asset.read",),
        skill_refs=("visual-critique@1.0.0",),
        context_policy="critic-v1",
        memory_read_scopes=(),
        memory_write_scopes=(),
        sandbox_execute=False,
        subagents=(),
        provenance_ref="agent-config://critic/1.0.0",
        content_hash="d" * 64,
    )
    skill = MaterializedSkill(
        skill_id="visual-critique",
        exact_version="1.0.0",
        path="/skills/visual-critique/1.0.0/SKILL.md",
        content_hash="e" * 64,
    )
    bundle = PinnedContextBundle(
        context_bundle_ref=request.context_bundle_ref,
        version="1.0.0",
        pinned_constraints="Logo geometry is immutable.",
        task_context="The current draft is artifact://poster/current.",
        source_refs=("artifact://poster/current",),
        content_hash="f" * 64,
    )
    raw_result = {
        "structured_response": {
            "status": "succeeded",
            "summary": (
                "Hierarchy is too flat; strengthen the primary headline."
            ),
            "decisions": [
                "Increase headline contrast before adding decoration"
            ],
            "artifact_refs": ["artifact://poster/critique-overlay"],
            "knowledge_refs": ["knowledge://critique/poster-1"],
            "proposed_operations": [
                {
                    "type": "design.adjust",
                    "target": "headline",
                    "priority": 1,
                }
            ],
            "open_questions": [],
            "confidence": "0.92",
        }
    }
    graph = FakeCompiledGraph(raw_result)
    provenance = DeepAgentProvenance(
        agent_id=config.agent_id,
        agent_version=config.exact_version,
        agent_config_hash=config.content_hash,
        context_bundle_ref=bundle.context_bundle_ref,
        context_hash=bundle.content_hash,
        skill_versions=("visual-critique@1.0.0",),
        tool_versions=("asset.read@1.0.0",),
        model_profile=config.model_profile,
        sandbox_execute=False,
    )
    compiled = CompiledDeepAgent(
        config=config,
        compiled_graph=graph,
        provenance=provenance,
        thread_id=f"deep:{run_id}:{task_id}:critic:1.0.0",
        effective_tools=("asset.read",),
    )
    result_store = MemoryResultStore()
    executor = DeepAgentTaskExecutor(
        requests=StaticRequestResolver(request),
        agents=StaticAgentResolver(config),
        skills=StaticSkillMaterializer((skill,)),
        contexts=StaticContextProvider(bundle),
        factory=StaticCompiledFactory(compiled),
        parser=StructuredResultParser(),
        results=result_store,
    )
    state = {
        "run_id": str(run_id),
        "organization_id": str(organization_id),
        "project_id": str(project_id),
        "task_id": str(task_id),
        "artifact_refs": ["artifact://poster/current"],
        "context_refs": [bundle.context_bundle_ref],
        "errors": [],
    }
    delta = asyncio.run(executor.execute(state))
    assert set(delta) == {"artifact_refs", "context_refs"}
    assert "artifact://poster/critique-overlay" in delta["artifact_refs"]
    assert "knowledge://critique/poster-1" in delta["context_refs"]
    assert delta["context_refs"][-1].startswith("agent-result://")
    assert len(result_store.items) == 1
    stored = result_store.items[0]
    assert stored.result.proposed_operations[0]["type"] == "design.adjust"
    assert "proposed_operations" not in delta
    invocation_message, invocation_config = graph.invocations[0]
    task_content = invocation_message["messages"][0]["content"]
    assert "Logo geometry is immutable" in task_content
    expected_thread = f"deep:{run_id}:{task_id}:critic:1.0.0"
    assert invocation_config["configurable"]["thread_id"] == expected_thread
    assert invocation_config["recursion_limit"] == config.max_steps

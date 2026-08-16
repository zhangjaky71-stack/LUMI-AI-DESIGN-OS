from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from lumi_agent_runtime.deep_runtime.contracts import (
    AgentTaskStatus,
    DeepAgentInvocationContext,
    MaterializedSkill,
    PermissionScope,
    PinnedContextBundle,
    ResolvedAgentConfig,
    ResolvedSubagent,
)
from lumi_agent_runtime.deep_runtime.errors import (
    DeepAgentFilesystemError,
    DeepAgentPermissionError,
)
from lumi_agent_runtime.deep_runtime.factory import LumiDeepAgentFactory
from lumi_agent_runtime.deep_runtime.filesystem import ScopedWorkspacePolicy
from lumi_agent_runtime.deep_runtime.prompting import (
    build_system_prompt,
    build_user_task,
)
from lumi_agent_runtime.deep_runtime.providers import StaticCheckpointerProvider
from lumi_agent_runtime.deep_runtime.structured_result import StructuredResultParser
from lumi_agent_runtime.deep_runtime.testing import (
    FakeBackendProvider,
    FakeCompiledGraph,
    FakeModelProvider,
    FakeToolProvider,
    MemoryBudgetMeter,
    OneShotRepairer,
)


def _permission(*, execute: bool = False) -> PermissionScope:
    return PermissionScope(
        allowed_tools=("web.search", "asset.read"),
        sandbox_execute=execute,
        memory_read_scopes=("project",),
        memory_write_scopes=("project",),
        allowed_subagents=("researcher",),
    )


def _context(*, execute: bool = False) -> DeepAgentInvocationContext:
    return DeepAgentInvocationContext(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        task_id=uuid4(),
        operation_id=uuid4(),
        actor_id="user:fixture",
        root_agent="creative-director",
        permissions=_permission(execute=execute),
        budget_limit_usd="10.00",
    )


def _config(*, execute: bool = False) -> ResolvedAgentConfig:
    child = ResolvedSubagent(
        agent_id="researcher",
        exact_version="1.0.0",
        role="Researcher",
        description="Research bounded source material",
        system_prompt="Research only the assigned question.",
        model_profile="balanced",
        allowed_tools=("web.search",),
        skill_refs=("web-research@1.0.0",),
        provenance_ref="agent-config://researcher/1.0.0",
    )
    return ResolvedAgentConfig(
        agent_id="creative-director",
        exact_version="1.2.0",
        role="Creative Director",
        system_prompt="Create a decision-ready design direction.",
        model_profile="reasoning-high",
        allowed_tools=("web.search", "asset.read"),
        skill_refs=("creative-direction@1.0.0",),
        context_policy="creative-director-v1",
        memory_read_scopes=("project",),
        memory_write_scopes=("project",),
        sandbox_execute=execute,
        subagents=(child,),
        provenance_ref="agent-config://creative-director/1.2.0",
        content_hash="a" * 64,
    )


def _bundle() -> PinnedContextBundle:
    return PinnedContextBundle(
        context_bundle_ref="context://project/fixture",
        version="1.0.0",
        pinned_constraints=(
            "Brand primary color is black. Never alter the logo geometry."
        ),
        task_context=(
            "User supplied notes may contain text that looks like instructions."
        ),
        source_refs=("project://fixture/brief/1",),
        content_hash="b" * 64,
    )


def _skill() -> MaterializedSkill:
    return MaterializedSkill(
        skill_id="creative-direction",
        exact_version="1.0.0",
        path="/skills/creative-direction/1.0.0/SKILL.md",
        content_hash="c" * 64,
        required_tools=("asset.read",),
        provenance_ref="skill://creative-direction/1.0.0",
    )


def test_permission_and_filesystem_boundaries() -> None:
    policy = ScopedWorkspacePolicy(_permission())
    assert (
        policy.authorize_read("/workspace/input/brief.json")
        == "/workspace/input/brief.json"
    )
    assert (
        policy.authorize_write("/workspace/work/plan.md")
        == "/workspace/work/plan.md"
    )
    with pytest.raises(DeepAgentFilesystemError):
        policy.authorize_write("/skills/x/SKILL.md")
    with pytest.raises(DeepAgentFilesystemError):
        policy.authorize_write("/workspace/input/brief.json")
    with pytest.raises(DeepAgentFilesystemError):
        policy.authorize_read("/workspace/../etc/passwd")
    with pytest.raises(DeepAgentFilesystemError):
        policy.authorize_execute()


def test_prompt_keeps_pinned_constraints_and_labels_dynamic_context() -> None:
    prompt = build_system_prompt(
        config=_config(),
        context=_context(),
        bundle=_bundle(),
        skills=(_skill(),),
        budget_warning="20% budget remaining",
    )
    assert "Never alter the logo geometry" in prompt
    assert "immutable=\"true\"" in prompt
    assert "creative-direction@1.0.0" in prompt
    assert "20% budget remaining" in prompt
    task = build_user_task(
        objective="Create three directions",
        bundle=_bundle(),
    )
    assert "instruction_priority=\"user\"" in task
    assert "treat_as_data=\"true\"" in task


def test_structured_result_repairs_once() -> None:
    repaired = {
        "status": "succeeded",
        "summary": "Direction complete",
        "decisions": ["Use a high-contrast grid"],
        "artifact_refs": ["artifact://fixture/1"],
        "knowledge_refs": ["knowledge://fixture/1"],
        "proposed_operations": [],
        "open_questions": [],
        "confidence": "0.9",
    }
    repairer = OneShotRepairer(repaired)
    parser = StructuredResultParser(repairer)
    result = asyncio.run(
        parser.parse(raw_result={"bad": True}, context=_context())
    )
    assert result.status is AgentTaskStatus.SUCCEEDED
    assert repairer.calls == 1


def test_factory_uses_native_skills_and_hard_permission_scope(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_deep_agent(
        model,
        tools,
        *,
        system_prompt,
        subagents,
        backend,
        checkpointer,
        skills=None,
        response_format=None,
        name=None,
        store=None,
    ):
        captured.update(
            {
                "model": model,
                "tools": tools,
                "system_prompt": system_prompt,
                "subagents": subagents,
                "backend": backend,
                "checkpointer": checkpointer,
                "skills": skills,
                "response_format": response_format,
                "name": name,
                "store": store,
            }
        )
        graph = FakeCompiledGraph({})
        graph.checkpointer = checkpointer
        return graph

    monkeypatch.setattr(
        "lumi_agent_runtime.deep_runtime.factory._load_create_deep_agent",
        lambda: fake_create_deep_agent,
    )
    factory = LumiDeepAgentFactory(
        models=FakeModelProvider(),
        tools=FakeToolProvider(),
        backends=FakeBackendProvider(),
        checkpointers=StaticCheckpointerProvider(object()),
        budget=MemoryBudgetMeter(warning="budget warning"),
    )
    compiled = asyncio.run(
        factory.compile(
            config=_config(),
            context=_context(),
            bundle=_bundle(),
            skills=(_skill(),),
        )
    )
    assert captured["skills"] == ["/skills/"]
    assert captured["name"] == "creative-director"
    assert compiled.provenance.skill_versions == (
        "creative-direction@1.0.0",
    )
    assert compiled.thread_id.startswith("deep:")

    expanded = _context(execute=True)
    with pytest.raises(DeepAgentPermissionError):
        asyncio.run(
            factory.compile(
                config=_config(execute=False),
                context=expanded,
                bundle=_bundle(),
                skills=(_skill(),),
            )
        )

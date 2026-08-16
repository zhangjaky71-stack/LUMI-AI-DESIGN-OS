from __future__ import annotations

from uuid import uuid4

import pytest

from lumi_agent_runtime.control_plane.checkpointing import memory_checkpointer
from lumi_agent_runtime.control_plane.contracts import (
    GraphDefinition,
    ResumeKind,
    ResumeRunCommand,
    RunStatus,
    StartRunCommand,
)
from lumi_agent_runtime.control_plane.main_graph import GRAPH_KEY, GRAPH_VERSION, build_main_graph
from lumi_agent_runtime.control_plane.ports import ControlServices
from lumi_agent_runtime.control_plane.runtime import (
    CompiledGraphRegistry,
    LangGraphControlPlane,
    LangGraphRuntime,
)
from lumi_agent_runtime.control_plane.testing import (
    AllowResumeAuthorizer,
    MemoryCancellationPort,
    MemoryEventSink,
    MemoryOperationGuard,
    MemoryRunControlStore,
    ScriptedExternalJobPort,
    ScriptedProjectPort,
    ScriptedQualityPort,
    ScriptedRecipePort,
    ScriptedTaskGraphPort,
    ScriptedTaskPort,
)


@pytest.mark.asyncio
async def test_rejected_approval_cannot_finalize_as_success() -> None:
    code_sha = "node28-reject-fixture"
    events = MemoryEventSink()
    cancellation = MemoryCancellationPort()
    services = ControlServices(
        project=ScriptedProjectPort(),
        recipes=ScriptedRecipePort(),
        tasks=ScriptedTaskGraphPort(["approval"]),
        deterministic=ScriptedTaskPort(),
        agentic=ScriptedTaskPort(),
        side_effects=ScriptedTaskPort(),
        external_jobs=ScriptedExternalJobPort(),
        quality=ScriptedQualityPort(["finalize"]),
        cancellation=cancellation,
        events=events,
    )
    graph = build_main_graph(services=services, checkpointer=memory_checkpointer())
    registry = CompiledGraphRegistry()
    registry.register(
        GraphDefinition(
            graph_key=GRAPH_KEY,
            graph_version=GRAPH_VERSION,
            code_git_sha=code_sha,
        ),
        graph,
    )
    plane = LangGraphControlPlane(
        runtime=LangGraphRuntime(registry),
        store=MemoryRunControlStore(),
        operation_guard=MemoryOperationGuard(),
        resume_authorizer=AllowResumeAuthorizer(),
        cancellation=cancellation,
        events=events,
    )
    start = StartRunCommand(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        operation_id=uuid4(),
        brief_version=1,
        budget_remaining="5.00",
        code_git_sha=code_sha,
    )
    waiting = await plane.start(start)
    result = await plane.resume(
        ResumeRunCommand(
            organization_id=start.organization_id,
            project_id=start.project_id,
            agent_run_id=start.agent_run_id,
            operation_id=uuid4(),
            thread_id=start.effective_thread_id,
            resume_version=waiting.resume_version,
            interrupt_id=str(waiting.interrupts[0]["id"]),
            kind=ResumeKind.APPROVAL,
            value={"action": "reject"},
            expected_graph_key=GRAPH_KEY,
            expected_graph_version=GRAPH_VERSION,
            expected_code_git_sha=code_sha,
        )
    )
    assert result.status is RunStatus.FAILED
    assert {item["code"] for item in result.state["errors"]} == {"APPROVAL_REJECTED"}
    assert not any(event.event_type == "run.completed" for event in events.events)

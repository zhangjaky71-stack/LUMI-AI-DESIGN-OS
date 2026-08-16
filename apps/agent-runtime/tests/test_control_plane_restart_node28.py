from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

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


def _services(events: MemoryEventSink, cancellation: MemoryCancellationPort) -> ControlServices:
    return ControlServices(
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


def _runtime(services: ControlServices, saver: Any, code_sha: str) -> LangGraphRuntime:
    graph = build_main_graph(services=services, checkpointer=saver)
    registry = CompiledGraphRegistry()
    registry.register(
        GraphDefinition(
            graph_key=GRAPH_KEY,
            graph_version=GRAPH_VERSION,
            code_git_sha=code_sha,
        ),
        graph,
    )
    return LangGraphRuntime(registry)


def test_resume_survives_control_plane_process_reconstruction() -> None:
    asyncio.run(_assert_resume_survives_control_plane_process_reconstruction())


async def _assert_resume_survives_control_plane_process_reconstruction() -> None:
    saver = memory_checkpointer()
    store = MemoryRunControlStore()
    guard = MemoryOperationGuard()
    events = MemoryEventSink()
    cancellation = MemoryCancellationPort()
    code_sha = "node28-restart-fixture"
    services = _services(events, cancellation)

    first_process = LangGraphControlPlane(
        runtime=_runtime(services, saver, code_sha),
        store=store,
        operation_guard=guard,
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
        budget_remaining="7.00",
        code_git_sha=code_sha,
    )
    waiting = await first_process.start(start)
    assert waiting.status is RunStatus.WAITING_USER

    second_process = LangGraphControlPlane(
        runtime=_runtime(services, saver, code_sha),
        store=store,
        operation_guard=guard,
        resume_authorizer=AllowResumeAuthorizer(),
        cancellation=cancellation,
        events=events,
    )
    completed = await second_process.resume(
        ResumeRunCommand(
            organization_id=start.organization_id,
            project_id=start.project_id,
            agent_run_id=start.agent_run_id,
            operation_id=uuid4(),
            thread_id=start.effective_thread_id,
            resume_version=waiting.resume_version,
            interrupt_id=str(waiting.interrupts[0]["id"]),
            kind=ResumeKind.APPROVAL,
            value={"action": "approve"},
            expected_graph_key=GRAPH_KEY,
            expected_graph_version=GRAPH_VERSION,
            expected_code_git_sha=code_sha,
        )
    )
    assert completed.status is RunStatus.SUCCEEDED
    assert completed.thread_id == start.effective_thread_id

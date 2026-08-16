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
    validate_run_state,
)
from lumi_agent_runtime.control_plane.errors import GraphVersionMismatch, ResumeVersionConflict
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

CODE_SHA = "node28-fixture-sha"


def _plane(routes: list[str], *, decisions: list[str] | None = None):
    events = MemoryEventSink()
    cancellation = MemoryCancellationPort()
    external = ScriptedExternalJobPort()
    services = ControlServices(
        project=ScriptedProjectPort(),
        recipes=ScriptedRecipePort(),
        tasks=ScriptedTaskGraphPort(routes),
        deterministic=ScriptedTaskPort({"artifact_refs": ["artifact://deterministic"]}),
        agentic=ScriptedTaskPort({"artifact_refs": ["artifact://agentic"]}),
        side_effects=ScriptedTaskPort({"artifact_refs": ["artifact://effect"]}),
        external_jobs=external,
        quality=ScriptedQualityPort(decisions),
        cancellation=cancellation,
        events=events,
    )
    graph = build_main_graph(services=services, checkpointer=memory_checkpointer())
    definition = GraphDefinition(
        graph_key=GRAPH_KEY,
        graph_version=GRAPH_VERSION,
        code_git_sha=CODE_SHA,
    )
    registry = CompiledGraphRegistry()
    registry.register(definition, graph)
    store = MemoryRunControlStore()
    guard = MemoryOperationGuard()
    plane = LangGraphControlPlane(
        runtime=LangGraphRuntime(registry),
        store=store,
        operation_guard=guard,
        resume_authorizer=AllowResumeAuthorizer(),
        cancellation=cancellation,
        events=events,
    )
    return plane, store, guard, events, external, cancellation


def _start() -> StartRunCommand:
    return StartRunCommand(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        operation_id=uuid4(),
        brief_version=1,
        budget_remaining="10.00",
        code_git_sha=CODE_SHA,
    )


@pytest.mark.asyncio
async def test_main_graph_completes_mock_run_and_replays_start_once() -> None:
    plane, _, guard, events, _, _ = _plane(["deterministic"])
    command = _start()
    first = await plane.start(command)
    second = await plane.start(command)
    assert first.status is RunStatus.SUCCEEDED
    assert second == first
    assert guard.executions == 1
    assert [event.event_type for event in events.events] == ["run.started", "run.completed"]


@pytest.mark.asyncio
async def test_approval_interrupt_resume_and_stale_version_fence() -> None:
    plane, _, _, events, _, _ = _plane(["approval"])
    start = _start()
    waiting = await plane.start(start)
    assert waiting.status is RunStatus.WAITING_USER
    interrupt_id = str(waiting.interrupts[0]["id"])
    resume = ResumeRunCommand(
        organization_id=start.organization_id,
        project_id=start.project_id,
        agent_run_id=start.agent_run_id,
        operation_id=uuid4(),
        thread_id=start.effective_thread_id,
        resume_version=waiting.resume_version,
        interrupt_id=interrupt_id,
        kind=ResumeKind.APPROVAL,
        value={"action": "approve"},
        expected_graph_key=GRAPH_KEY,
        expected_graph_version=GRAPH_VERSION,
        expected_code_git_sha=CODE_SHA,
    )
    completed = await plane.resume(resume)
    assert completed.status is RunStatus.SUCCEEDED
    assert completed.resume_version == waiting.resume_version + 1
    assert "approval.required" in [event.event_type for event in events.events]

    stale = ResumeRunCommand(
        organization_id=start.organization_id,
        project_id=start.project_id,
        agent_run_id=start.agent_run_id,
        operation_id=uuid4(),
        thread_id=start.effective_thread_id,
        resume_version=waiting.resume_version,
        interrupt_id=interrupt_id,
        kind=ResumeKind.APPROVAL,
        value={"action": "approve"},
        expected_graph_key=GRAPH_KEY,
        expected_graph_version=GRAPH_VERSION,
        expected_code_git_sha=CODE_SHA,
    )
    with pytest.raises((ResumeVersionConflict, Exception)):
        await plane.resume(stale)


@pytest.mark.asyncio
async def test_external_job_wait_resumes_same_thread() -> None:
    plane, _, _, events, external, _ = _plane(["wait_external"])
    start = _start()
    waiting = await plane.start(start)
    assert waiting.status is RunStatus.WAITING_EXTERNAL
    item = waiting.interrupts[0]
    assert item["payload"]["job_id"] == external.job_id
    resume = ResumeRunCommand(
        organization_id=start.organization_id,
        project_id=start.project_id,
        agent_run_id=start.agent_run_id,
        operation_id=uuid4(),
        thread_id=start.effective_thread_id,
        resume_version=waiting.resume_version,
        interrupt_id=str(item["id"]),
        kind=ResumeKind.EXTERNAL_JOB,
        value={"job_id": external.job_id},
        expected_graph_key=GRAPH_KEY,
        expected_graph_version=GRAPH_VERSION,
        expected_code_git_sha=CODE_SHA,
    )
    completed = await plane.resume(resume)
    assert completed.status is RunStatus.SUCCEEDED
    assert completed.thread_id == waiting.thread_id
    assert external.collect_calls == 1
    assert "run.waiting_external" in [event.event_type for event in events.events]


@pytest.mark.asyncio
async def test_resume_rejects_graph_version_drift() -> None:
    plane, _, _, _, _, _ = _plane(["approval"])
    start = _start()
    waiting = await plane.start(start)
    command = ResumeRunCommand(
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
        expected_graph_version="2.0.0",
        expected_code_git_sha=CODE_SHA,
    )
    with pytest.raises(GraphVersionMismatch):
        await plane.resume(command)


@pytest.mark.asyncio
async def test_cancel_releases_pending_work_and_budget() -> None:
    plane, _, _, _, _, cancellation = _plane(["approval"])
    start = _start()
    await plane.start(start)
    cancelled = await plane.cancel(
        organization_id=start.organization_id,
        project_id=start.project_id,
        agent_run_id=start.agent_run_id,
        operation_id=uuid4(),
    )
    assert cancelled.status is RunStatus.CANCELLED
    assert cancellation.cancel_calls == 1
    assert cancellation.release_calls == 1


def test_graph_state_rejects_binary_and_inline_data_uri() -> None:
    with pytest.raises(ValueError):
        validate_run_state({"errors": [{"blob": b"secret"}]})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="GRAPH_STATE_INLINE_DATA_URI_FORBIDDEN"):
        validate_run_state({"artifact_refs": ["data:image/png;base64,AAAA"]})  # type: ignore[arg-type]

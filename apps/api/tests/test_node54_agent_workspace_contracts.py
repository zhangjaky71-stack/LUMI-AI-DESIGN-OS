from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from lumi_api.api.v1.agent_workspace_adapter import ControlStoreAgentWorkspaceService
from lumi_api.api.v1.agent_workspace_schemas import AgentRunSafeEventResponse


@dataclass
class Snapshot:
    project_id: UUID
    agent_run_id: UUID
    task_id: UUID | None
    thread_id: str
    graph_key: str
    graph_version: str
    code_git_sha: str
    status: str
    checkpoint_id: str | None
    state: dict[str, Any]
    next_nodes: tuple[str, ...]
    interrupts: tuple[dict[str, Any], ...]
    resume_version: int
    error_code: str | None
    updated_at: datetime


class Store:
    def __init__(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot

    async def load(self, *, organization_id: UUID, agent_run_id: UUID):
        if agent_run_id != self.snapshot.agent_run_id:
            return None
        return self.snapshot


class Replay:
    def __init__(self, event: AgentRunSafeEventResponse) -> None:
        self.event = event
        self.after_event_id: str | None = None

    async def replay(self, *, organization_id: UUID, agent_run_id: UUID, after_event_id: str | None):
        self.after_event_id = after_event_id
        yield self.event


def test_workspace_projection_hides_raw_state_and_interrupt_payload() -> None:
    asyncio.run(_projection_hides_raw_state())


async def _projection_hides_raw_state() -> None:
    organization_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    snapshot = Snapshot(
        project_id=project_id,
        agent_run_id=run_id,
        task_id=None,
        thread_id="thread-1",
        graph_key="lumi.main",
        graph_version="1.0.0",
        code_git_sha="a" * 40,
        status="waiting_user",
        checkpoint_id="checkpoint-1",
        state={
            "context_refs": ["context://one"],
            "artifact_refs": ["artifact-version://one"],
            "budget_remaining": "3.25",
            "route": "approval",
            "repair_iteration": 1,
            "max_repair_iterations": 2,
            "errors": [{"internal": "must not project"}],
        },
        next_nodes=("approval_interrupt",),
        interrupts=(
            {
                "id": "interrupt-1",
                "kind": "approval",
                "node": "approval_interrupt",
                "resumable": True,
                "payload": {"private_internal": "not projected"},
            },
        ),
        resume_version=4,
        error_code=None,
        updated_at=datetime.now(UTC),
    )
    event = AgentRunSafeEventResponse(
        event_id="event-1",
        event_type="approval.required",
        agent_run_id=run_id,
        project_id=project_id,
        occurred_at=datetime.now(UTC),
        payload={"interrupt_id": "interrupt-1"},
    )
    service = ControlStoreAgentWorkspaceService(
        control_store=Store(snapshot),
        event_replay=Replay(event),
    )
    projected = await service.get_control(
        organization_id=organization_id,
        agent_run_id=run_id,
        request_context=None,
    )
    payload = projected.model_dump(mode="json")
    assert "state" not in payload
    assert "payload" not in payload["interrupts"][0]
    assert payload["artifact_refs"] == ["artifact-version://one"]
    assert payload["resume_version"] == 4


def test_safe_event_schema_rejects_private_reasoning_recursively() -> None:
    with pytest.raises(ValidationError, match="AGENT_WORKSPACE_PRIVATE_EVENT_FIELD_FORBIDDEN"):
        AgentRunSafeEventResponse(
            event_id="event-1",
            event_type="agent.delta",
            agent_run_id=uuid4(),
            project_id=uuid4(),
            occurred_at=datetime.now(UTC),
            payload={"nested": {"reasoning": "private"}},
        )


def test_event_replay_preserves_last_event_cursor() -> None:
    asyncio.run(_event_replay_preserves_cursor())


async def _event_replay_preserves_cursor() -> None:
    organization_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    snapshot = Snapshot(
        project_id=project_id,
        agent_run_id=run_id,
        task_id=None,
        thread_id="thread-1",
        graph_key="lumi.main",
        graph_version="1.0.0",
        code_git_sha="b" * 40,
        status="running",
        checkpoint_id="checkpoint-1",
        state={},
        next_nodes=(),
        interrupts=(),
        resume_version=1,
        error_code=None,
        updated_at=datetime.now(UTC),
    )
    event = AgentRunSafeEventResponse(
        event_id="event-2",
        event_type="agent.status",
        agent_run_id=run_id,
        project_id=project_id,
        occurred_at=datetime.now(UTC),
        payload={"status": "working"},
    )
    replay = Replay(event)
    service = ControlStoreAgentWorkspaceService(
        control_store=Store(snapshot),
        event_replay=replay,
    )
    received = [
        item
        async for item in service.stream_events(
            organization_id=organization_id,
            agent_run_id=run_id,
            after_event_id="event-1",
            request_context=None,
        )
    ]
    assert replay.after_event_id == "event-1"
    assert [item.event_id for item in received] == ["event-2"]

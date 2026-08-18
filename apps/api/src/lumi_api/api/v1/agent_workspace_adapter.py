from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol
from uuid import UUID

from .agent_workspace_schemas import (
    AgentRunInterruptResponse,
    AgentRunSafeEventResponse,
    AgentRunWorkspaceControlResponse,
)
from .errors import ApiProblem


class RunControlSnapshotLike(Protocol):
    project_id: UUID
    agent_run_id: UUID
    task_id: UUID | None
    thread_id: str
    graph_key: str
    graph_version: str
    code_git_sha: str
    status: Any
    checkpoint_id: str | None
    state: dict[str, Any]
    next_nodes: tuple[str, ...]
    interrupts: tuple[dict[str, Any], ...]
    resume_version: int
    error_code: str | None
    updated_at: Any


class RunControlReader(Protocol):
    async def load(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
    ) -> RunControlSnapshotLike | None: ...


class AgentEventReplayPort(Protocol):
    def replay(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        after_event_id: str | None,
    ) -> AsyncIterator[AgentRunSafeEventResponse]: ...


class ControlStoreAgentWorkspaceService:
    """Public projection over NODE-28 control state + durable event replay."""

    def __init__(
        self,
        *,
        control_store: RunControlReader,
        event_replay: AgentEventReplayPort,
    ) -> None:
        self.control_store = control_store
        self.event_replay = event_replay

    async def get_control(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        request_context: object,
    ) -> AgentRunWorkspaceControlResponse:
        snapshot = await self._load(organization_id, agent_run_id)
        state = snapshot.state
        return AgentRunWorkspaceControlResponse(
            agent_run_id=snapshot.agent_run_id,
            project_id=snapshot.project_id,
            task_id=snapshot.task_id,
            thread_id=snapshot.thread_id,
            graph_key=snapshot.graph_key,
            graph_version=snapshot.graph_version,
            code_git_sha=snapshot.code_git_sha,
            status=_enum_value(snapshot.status),
            checkpoint_id=snapshot.checkpoint_id,
            resume_version=snapshot.resume_version,
            next_nodes=list(snapshot.next_nodes),
            interrupts=[_public_interrupt(item) for item in snapshot.interrupts],
            context_refs=_string_list(state.get("context_refs")),
            artifact_refs=_string_list(state.get("artifact_refs")),
            budget_remaining=_optional_string(state.get("budget_remaining")),
            route=_optional_string(state.get("route")),
            repair_iteration=_nonnegative_int(state.get("repair_iteration")),
            max_repair_iterations=_nonnegative_int(state.get("max_repair_iterations")),
            error_code=snapshot.error_code,
            updated_at=snapshot.updated_at,
        )

    async def stream_events(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        after_event_id: str | None,
        request_context: object,
    ) -> AsyncIterator[AgentRunSafeEventResponse]:
        snapshot = await self._load(organization_id, agent_run_id)
        async for event in self.event_replay.replay(
            organization_id=organization_id,
            agent_run_id=agent_run_id,
            after_event_id=after_event_id,
        ):
            if event.agent_run_id != agent_run_id or event.project_id != snapshot.project_id:
                raise ApiProblem(
                    status=503,
                    code="agent_event_scope_mismatch",
                    title="Agent event replay invalid",
                    detail="The event replay source returned an event outside the canonical run scope.",
                )
            yield event

    async def _load(
        self,
        organization_id: UUID,
        agent_run_id: UUID,
    ) -> RunControlSnapshotLike:
        snapshot = await self.control_store.load(
            organization_id=organization_id,
            agent_run_id=agent_run_id,
        )
        if snapshot is None:
            raise ApiProblem(
                status=404,
                code="agent_run_control_not_found",
                title="Agent run control not found",
                detail="No canonical control snapshot exists for this tenant-scoped run.",
            )
        return snapshot


def _public_interrupt(item: dict[str, Any]) -> AgentRunInterruptResponse:
    interrupt_id = item.get("id")
    kind = item.get("kind")
    if not isinstance(interrupt_id, str) or not interrupt_id:
        raise ApiProblem(
            status=503,
            code="agent_interrupt_invalid",
            title="Agent control state invalid",
            detail="Interrupt id is missing from canonical control state.",
        )
    if not isinstance(kind, str) or not kind:
        raise ApiProblem(
            status=503,
            code="agent_interrupt_invalid",
            title="Agent control state invalid",
            detail="Interrupt kind is missing from canonical control state.",
        )
    node = item.get("node")
    return AgentRunInterruptResponse(
        id=interrupt_id,
        kind=kind,
        node=node if isinstance(node, str) else None,
        resumable=bool(item.get("resumable", True)),
    )


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    if not isinstance(raw, str) or not raw:
        raise ValueError("AGENT_CONTROL_STATUS_INVALID")
    return raw


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("AGENT_CONTROL_STRING_LIST_INVALID")
    return list(value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("AGENT_CONTROL_STRING_INVALID")
    return value


def _nonnegative_int(value: Any) -> int:
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("AGENT_CONTROL_INTEGER_INVALID")
    return value

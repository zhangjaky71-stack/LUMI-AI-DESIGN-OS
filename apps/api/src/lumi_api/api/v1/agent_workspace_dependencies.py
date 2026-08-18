from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, Request

from .agent_workspace_schemas import (
    AgentRunSafeEventResponse,
    AgentRunWorkspaceControlResponse,
)
from .errors import ApiProblem


class AgentWorkspaceService(Protocol):
    async def get_control(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        request_context: object,
    ) -> AgentRunWorkspaceControlResponse: ...

    def stream_events(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        after_event_id: str | None,
        request_context: object,
    ) -> AsyncIterator[AgentRunSafeEventResponse]: ...


def get_agent_workspace_service(request: Request) -> AgentWorkspaceService:
    service = getattr(request.app.state, "agent_workspace_service", None)
    if service is None:
        raise ApiProblem(
            status=503,
            code="agent_workspace_runtime_not_composed",
            title="Agent workspace runtime unavailable",
            detail=(
                "The canonical run snapshot/event replay service is not composed "
                "in this deployment."
            ),
        )
    return service


AgentWorkspaceServiceDependency = Annotated[
    AgentWorkspaceService,
    Depends(get_agent_workspace_service),
]

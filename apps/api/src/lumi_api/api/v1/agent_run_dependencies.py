from __future__ import annotations

from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import Depends, Request

from .errors import ApiProblem


class AgentRunControlService(Protocol):
    async def resume(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        operation_id: UUID,
        resume_version: int,
        interrupt_id: str,
        kind: str,
        value: Any,
        request_context: Any,
    ) -> dict[str, Any]: ...

    async def cancel(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        operation_id: UUID,
        request_context: Any,
    ) -> dict[str, Any]: ...


def get_agent_run_control_service(request: Request) -> AgentRunControlService:
    service = getattr(request.app.state, "agent_run_control_service", None)
    if service is None:
        raise ApiProblem(
            status=503,
            code="agent_runtime_not_composed",
            title="Agent runtime unavailable",
            detail="The LangGraph control-plane service is not composed in this deployment.",
        )
    return service


AgentRunControlServiceDependency = Annotated[
    AgentRunControlService,
    Depends(get_agent_run_control_service),
]

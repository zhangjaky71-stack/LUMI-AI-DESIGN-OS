from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request

from .agent_run_dependencies import AgentRunControlServiceDependency
from .agent_run_schemas import (
    AgentRunCancelRequest,
    AgentRunControlResponse,
    AgentRunResumeRequest,
)
from .headers import OrganizationId

router = APIRouter(prefix="/api/v1/agent-runs", tags=["agent-runs"])


@router.post("/{agent_run_id}/resume", response_model=AgentRunControlResponse)
async def resume_agent_run(
    agent_run_id: UUID,
    body: AgentRunResumeRequest,
    request: Request,
    organization_id: OrganizationId,
    service: AgentRunControlServiceDependency,
) -> AgentRunControlResponse:
    result = await service.resume(
        organization_id=organization_id,
        agent_run_id=agent_run_id,
        operation_id=body.operation_id,
        resume_version=body.resume_version,
        interrupt_id=body.interrupt_id,
        kind=body.kind,
        value=body.value,
        request_context=_context(request),
    )
    return AgentRunControlResponse.model_validate(result)


@router.post("/{agent_run_id}/cancel", response_model=AgentRunControlResponse)
async def cancel_agent_run(
    agent_run_id: UUID,
    body: AgentRunCancelRequest,
    request: Request,
    organization_id: OrganizationId,
    service: AgentRunControlServiceDependency,
) -> AgentRunControlResponse:
    result = await service.cancel(
        organization_id=organization_id,
        agent_run_id=agent_run_id,
        operation_id=body.operation_id,
        request_context=_context(request),
    )
    return AgentRunControlResponse.model_validate(result)


def _context(request: Request) -> Any:
    return getattr(request.state, "lumi_context", None)

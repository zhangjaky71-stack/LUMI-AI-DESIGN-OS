from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from .agent_workspace_dependencies import AgentWorkspaceServiceDependency
from .agent_workspace_schemas import AgentRunWorkspaceControlResponse
from .headers import OrganizationId

router = APIRouter(prefix="/api/v1/agent-runs", tags=["agent-workspace"])


@router.get(
    "/{agent_run_id}/control",
    response_model=AgentRunWorkspaceControlResponse,
)
async def get_agent_run_control(
    agent_run_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    service: AgentWorkspaceServiceDependency,
) -> AgentRunWorkspaceControlResponse:
    return await service.get_control(
        organization_id=organization_id,
        agent_run_id=agent_run_id,
        request_context=_context(request),
    )


@router.get("/{agent_run_id}/events")
async def stream_agent_run_events(
    agent_run_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    service: AgentWorkspaceServiceDependency,
    last_event_id: Annotated[
        str | None,
        Header(alias="Last-Event-ID", max_length=256),
    ] = None,
) -> StreamingResponse:
    async def body():
        async for event in service.stream_events(
            organization_id=organization_id,
            agent_run_id=agent_run_id,
            after_event_id=last_event_id,
            request_context=_context(request),
        ):
            if await request.is_disconnected():
                break
            payload = json.dumps(
                event.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            yield (
                f"id: {event.event_id}\n"
                f"event: {event.event_type}\n"
                f"data: {payload}\n\n"
            ).encode("utf-8")

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _context(request: Request) -> object:
    return getattr(request.state, "lumi_context", None)
